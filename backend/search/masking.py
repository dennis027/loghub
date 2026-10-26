"""Read-time masking applied on top of the ingest-time redaction in Fluent Bit/Logstash."""

from core.permissions import ROLE_ANALYST, has_role

# Personal data hidden from viewers; analysts and above see them.
VIEWER_HIDDEN_FIELDS = ('user', 'client_ip', 'raw')
MASK = '[MASKED]'


def _mask_path(doc, dotted):
    parts = dotted.split('.')
    node = doc
    for part in parts[:-1]:
        node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            return
    if isinstance(node, dict) and parts[-1] in node:
        node[parts[-1]] = MASK


def mask_hit(hit, user, organization):
    fields = list(organization.masked_fields or [])
    if not has_role(user, ROLE_ANALYST):
        fields.extend(VIEWER_HIDDEN_FIELDS)
    for field in fields:
        _mask_path(hit['source'], field)
        if field in hit:
            hit[field] = MASK
    return hit
