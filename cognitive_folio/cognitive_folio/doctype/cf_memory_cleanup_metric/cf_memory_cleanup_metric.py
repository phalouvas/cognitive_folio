from frappe.model.document import Document


class CFMemoryCleanupMetric(Document):
    """Daily rollup of vector-memory cleanup executions."""
