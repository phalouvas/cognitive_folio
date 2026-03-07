# pyright: reportMissingImports=false
try:
    import frappe
except Exception:  # pragma: no cover - fallback for non-Frappe test runs
    frappe = None


class BatchDatabaseWriter:
    """Batch small DB writes to reduce repeated round-trips."""

    def __init__(self):
        self._operations = []

    def add_set_value(self, doctype, name, fieldname, value, update_modified=False):
        self._operations.append(("set_value", doctype, name, fieldname, value, bool(update_modified)))

    def add_doc_update(self, document):
        self._operations.append(("doc_update", document))

    def flush(self, commit=False):
        applied = 0
        if not frappe:
            self._operations = []
            return {"applied": applied, "committed": False}

        for operation in self._operations:
            kind = operation[0]
            if kind == "set_value":
                _, doctype, name, fieldname, value, update_modified = operation
                frappe.db.set_value(doctype, name, fieldname, value, update_modified=update_modified)
                applied += 1
            elif kind == "doc_update":
                _, document = operation
                document.db_update()
                applied += 1

        self._operations = []
        if commit:
            frappe.db.commit()

        return {"applied": applied, "committed": bool(commit)}


class ConnectionPooling:
    """Expose basic DB connection diagnostics for observability."""

    def snapshot(self):
        if not frappe:
            return {"available": False}

        db = getattr(frappe, "db", None)
        if not db:
            return {"available": False}

        conn = getattr(db, "_conn", None)
        return {
            "available": conn is not None,
            "db_type": getattr(db, "db_type", None),
            "autocommit": bool(getattr(conn, "autocommit", False)) if conn is not None else None,
        }


class QueryOptimization:
    @staticmethod
    def chunked(items, chunk_size):
        size = max(1, int(chunk_size or 1))
        sequence = list(items or [])
        for idx in range(0, len(sequence), size):
            yield sequence[idx: idx + size]


class IndexManagement:
    """Small helper to create missing indexes for high-traffic tables."""

    def ensure_indexes(self, specs):
        if not frappe:
            return {"created": [], "existing": [], "failed": []}

        created = []
        existing = []
        failed = []

        for spec in specs or []:
            doctype = spec.get("doctype")
            index_name = spec.get("index_name")
            columns = spec.get("columns") or []
            if not doctype or not index_name or not columns:
                failed.append({"spec": spec, "error": "invalid_spec"})
                continue

            table = f"tab{doctype}"
            col_expr = ", ".join([f"`{col}`" for col in columns])
            try:
                existing_rows = frappe.db.sql(
                    f"SHOW INDEX FROM `{table}` WHERE Key_name = %s",
                    (index_name,),
                    as_dict=True,
                )
                if existing_rows:
                    existing.append(index_name)
                    continue

                frappe.db.sql(f"ALTER TABLE `{table}` ADD INDEX `{index_name}` ({col_expr})")
                created.append(index_name)
            except Exception as exc:
                failed.append({"index": index_name, "error": str(exc)})

        return {
            "created": created,
            "existing": existing,
            "failed": failed,
        }
