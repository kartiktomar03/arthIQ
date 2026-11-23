"""Build the two pgAdmin import entry points from an independently profiled CSV directory."""
import argparse
import json
from pathlib import Path

from source_profile import COLUMNS, FOREIGN_KEYS, KEYS, LINKS, filename, orphan_sql, profile

HERE = Path(__file__).resolve().parent
ROLE = "arthiq_olist_analytics"


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def fragment(name):
    return (HERE / name).read_text(encoding="utf-8-sig").strip()


def generate(folder, source, client):
    sql = [r"\set ON_ERROR_STOP on" if client else "-- pgAdmin Query Tool: execute the entire file on arthiq_olist.",
           """BEGIN;
DO $guard$
BEGIN
 IF current_database() <> 'arthiq_olist' THEN
   RAISE EXCEPTION 'Wrong database: select arthiq_olist. Nothing imported.';
 END IF;
 IF NOT pg_try_advisory_xact_lock(204885, 913) THEN
   RAISE EXCEPTION 'Another Olist import is running.';
 END IF;
END $guard$;
SET LOCAL search_path=pg_catalog, pg_temp;
SET LOCAL standard_conforming_strings=on;
SET LOCAL DateStyle='ISO, YMD';
CREATE TEMP TABLE arthiq_run ON COMMIT DROP AS
 SELECT clock_timestamp() AS started, to_regnamespace('olist') IS NULL AS fresh;
CREATE TEMP TABLE arthiq_facts (k text PRIMARY KEY, v jsonb NOT NULL) ON COMMIT DROP;
CREATE TEMP TABLE IF NOT EXISTS arthiq_olist_last_report (report jsonb) ON COMMIT PRESERVE ROWS;
DELETE FROM pg_temp.arthiq_olist_last_report;
DO $setup$
BEGIN
 IF (SELECT fresh FROM pg_temp.arthiq_run) THEN
   IF to_regrole('arthiq_olist_analytics') IS NOT NULL THEN
     RAISE EXCEPTION 'Existing Olist role is unmanaged by this import; inspect it before proceeding.';
   END IF;
""" + fragment("001_tables.sql") + """
 ELSE
   IF obj_description(to_regnamespace('olist'),'pg_namespace') IS DISTINCT FROM 'ArthIQ Olist standalone import v1'
      OR shobj_description(to_regrole('arthiq_olist_analytics'),'pg_authid') IS DISTINCT FROM 'ArthIQ Olist standalone reader v1' THEN
     RAISE EXCEPTION 'Existing schema or role is unmanaged. Import stopped.';
   END IF;
 END IF;
END $setup$;"""]
    # All SQL identifiers originate from fixed project constants. Only the COPY filename varies.
    for t,names in COLUMNS.items():
        fields=",".join(names.split())
        path=(folder/filename(t)).resolve().as_posix()
        if any(c in path for c in "\r\n'"):
            raise ValueError("Use a local CSV folder without quotes or line breaks in its path.")
        sql.append(f"CREATE TEMP TABLE src_{t} (LIKE olist.{t}) ON COMMIT DROP;")
        command= r"\copy" if client else "COPY"
        suffix="" if client else ";"
        sql.append(f"{command} pg_temp.src_{t} ({fields}) FROM {literal(path)} WITH (FORMAT CSV, HEADER MATCH, ENCODING 'UTF8', FORCE_NULL ({fields})){suffix}")
        sql.append(f"""DO $load$
BEGIN
 IF (SELECT fresh FROM pg_temp.arthiq_run) THEN
   INSERT INTO olist.{t} ({fields}) SELECT {fields} FROM pg_temp.src_{t};
 ELSE
   LOCK TABLE olist.{t} IN SHARE MODE;
   IF EXISTS ((SELECT * FROM pg_temp.src_{t} EXCEPT ALL SELECT * FROM olist.{t})
        UNION ALL (SELECT * FROM olist.{t} EXCEPT ALL SELECT * FROM pg_temp.src_{t})) THEN
      RAISE EXCEPTION 'Existing {t} differs from CSV; left untouched.';
   END IF;
 END IF;
END $load$;""")
    sql.append("DO $finish$ BEGIN IF (SELECT fresh FROM pg_temp.arthiq_run) THEN\n"
               +fragment("002_relationships.sql")+"\n"+fragment("003_reader.sql")+"\nEND IF; END $finish$;")
    for t,names in COLUMNS.items():
        col_counts=", ".join(f"'{c}',count(*) FILTER (WHERE {c} IS NULL)" for c in names.split())
        expected=source["tables"][t]
        sql.append(f"""INSERT INTO pg_temp.arthiq_facts SELECT '{t}', jsonb_build_object(
 'csv_rows', {expected['rows']}, 'pg_rows', count(*), 'nulls',jsonb_build_object({col_counts}))
 FROM olist.{t};""")
        # Verify parsed records including legitimate duplicate multiplicity.
        sql.append(f"""DO $check$ DECLARE v jsonb; BEGIN
 SELECT f.v INTO STRICT v FROM pg_temp.arthiq_facts f WHERE k='{t}';
 IF (v->>'pg_rows')::bigint <> {expected['rows']} OR v->'nulls' <> {literal(json.dumps(expected['nulls']))}::jsonb THEN
   RAISE EXCEPTION '{t}: count or NULL reconciliation failed';
 END IF;
END $check$;""")
        def excess(key):
            return f"(SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM olist.{t} GROUP BY {key} HAVING count(*)>1) g)"
        parts=', '.join(literal(k)+','+excess(k) for k in expected['duplicate_key_excess'])
        sql.append(f"""UPDATE pg_temp.arthiq_facts SET v=v || jsonb_build_object(
 'duplicate_key_excess',jsonb_build_object({parts}), 'identical_typed_row_excess',{excess(','.join(names.split()))},
 'csv_identical_row_excess',{expected['identical_row_excess']}) WHERE k='{t}';""")
        sql.append(f"""DO $check$ BEGIN
 IF (SELECT v->'duplicate_key_excess' FROM pg_temp.arthiq_facts WHERE k='{t}') <>
 {literal(json.dumps(expected['duplicate_key_excess']))}::jsonb THEN RAISE EXCEPTION '{t}: key reconciliation failed'; END IF;
END $check$;""")
    parts=[]
    for link in LINKS:
        t,c,parent,pk=link
        key=f"{t}.{c} -> {parent}.{pk}"
        parts.extend([literal(key),"("+orphan_sql(link,"olist.")+")"])
    sql.append("INSERT INTO pg_temp.arthiq_facts VALUES ('orphan_rows',jsonb_build_object("+",".join(parts)+"));")
    sql.append(f"""DO $check$ BEGIN
 IF (SELECT v FROM pg_temp.arthiq_facts WHERE k='orphan_rows') <> {literal(json.dumps(source['orphan_rows']))}::jsonb
 THEN RAISE EXCEPTION 'Orphan reconciliation failed'; END IF;
END $check$;""")
    refs=fragment("reference.sql").rstrip(";")
    sql.append(f"""SET LOCAL ROLE {ROLE};
DO $reader$ DECLARE actual jsonb; BEGIN
 IF NOT has_database_privilege(current_database(),'CONNECT') OR NOT has_schema_privilege('olist','USAGE') OR
    EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND
    (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)) OR
    EXISTS(SELECT 1 FROM pg_auth_members WHERE member=to_regrole(current_user)) OR
    has_database_privilege(current_database(),'CREATE,TEMP') OR
    EXISTS(SELECT 1 FROM pg_namespace WHERE has_schema_privilege(oid,'CREATE')) OR
    EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='olist' AND c.relkind='r' AND
            (has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') OR
             NOT has_table_privilege(c.oid,'SELECT') OR c.relowner=to_regrole(current_user))) THEN
   RAISE EXCEPTION 'Reader effective privilege check failed';
 END IF;
 SELECT to_jsonb(r) INTO actual FROM ({refs}) r;
 IF actual <> {literal(json.dumps(source['source_reference']))}::jsonb THEN
   RAISE EXCEPTION 'Reference SQL differs from independent CSV calculations'; END IF;
END $reader$;
RESET ROLE;
INSERT INTO pg_temp.arthiq_facts SELECT 'reference_sql',to_jsonb(r) FROM ({refs}) r;
DO $catalog$ BEGIN
 IF (SELECT count(*) FROM pg_constraint WHERE connamespace='olist'::regnamespace AND contype='f' AND convalidated) <> 6
 OR (SELECT count(*) FROM pg_constraint WHERE connamespace='olist'::regnamespace AND contype='p') <> 8
 OR (SELECT count(*) FROM pg_indexes WHERE schemaname='olist') <> 17 THEN
   RAISE EXCEPTION 'Unexpected Olist constraints or indexes; inspect existing schema';
 END IF;
END $catalog$;
INSERT INTO pg_temp.arthiq_facts SELECT 'constraints',jsonb_agg(jsonb_build_object(
 'table',conrelid::regclass::text,'name',conname,'definition',pg_get_constraintdef(oid)) ORDER BY conname)
 FROM pg_constraint WHERE connamespace='olist'::regnamespace AND contype IN ('p','f');
INSERT INTO pg_temp.arthiq_facts SELECT 'indexes',jsonb_agg(indexdef ORDER BY indexname) FROM pg_indexes WHERE schemaname='olist';
INSERT INTO pg_temp.arthiq_olist_last_report SELECT jsonb_object_agg(k,v) || jsonb_build_object(
 'database',current_database(),'reader_role','{ROLE}','reader_privileges_verified',true,
 'mode',(SELECT CASE WHEN fresh THEN 'first import' ELSE 'verified existing import' END FROM pg_temp.arthiq_run),
 'skipped_rows',0,'rejected_rows',0,'elapsed_seconds',extract(epoch FROM clock_timestamp()-(SELECT started FROM pg_temp.arthiq_run)))
 FROM pg_temp.arthiq_facts;
COMMIT;
SELECT jsonb_pretty(report) AS verified_import_report FROM pg_temp.arthiq_olist_last_report;""")
    return "\n\n".join(sql)+"\n"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_dir",type=Path)
    a=p.parse_args()
    result=profile(a.csv_dir)
    for t,key in KEYS.items():
        s=result["tables"][t]
        if s["duplicate_key_excess"][key] or any(s["nulls"][c] for c in key.split(",")):
            p.error(f"{t}: source violates planned primary key")
    for t,c,parent,pk in FOREIGN_KEYS:
        key=f"{t}.{c} -> {parent}.{pk}"
        if result["orphan_rows"][key]:p.error(f"Source violates planned foreign key: {key}")
    for name,client in [("run_in_pgadmin.sql",False),("run_in_psql.sql",True)]:
        (HERE/name).write_text(generate(a.csv_dir,result,client),encoding="utf8")
    (HERE/"source-report.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print("Prepared both drivers and source-report.json. No PostgreSQL connection was opened.")


if __name__=="__main__":
    main()
