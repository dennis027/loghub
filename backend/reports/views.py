import csv
import io

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_audit
from core.exceptions import InvalidQuery
from core.permissions import ROLE_ANALYST, has_role
from search.query import parse_relative

from .generators import REPORT_TITLES, REPORTS


def _pdf(report, org, range_):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=report['title'])
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"{report['title']} — {org.name}", styles['Title']),
        Paragraph(f'Range: last {range_} · generated {timezone.now():%Y-%m-%d %H:%M} UTC', styles['Normal']),
        Spacer(1, 12),
    ]
    if report['summary']:
        story.append(Paragraph(' · '.join(f'{k}: {v}' for k, v in report['summary'].items()), styles['Normal']))
        story.append(Spacer(1, 12))

    # Paragraph cells escape markup from untrusted values.
    def cell(v):
        from xml.sax.saxutils import escape

        return Paragraph(escape(str(v if v is not None else ''))[:300], styles['BodyText'])

    data = [report['columns']] + [[cell(v) for v in row] for row in report['rows'][:2000]]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d1d5db')),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]
        )
    )
    story.append(table if report['rows'] else Paragraph('No data in this range.', styles['Italic']))
    doc.build(story)
    return buf.getvalue()


class ReportListView(APIView):
    def get(self, request):
        return Response([{'key': k, 'title': REPORT_TITLES[k]} for k in REPORTS])


class ReportView(APIView):
    def get(self, request, key):
        generator = REPORTS.get(key)
        if generator is None:
            raise NotFound('Unknown report.')
        range_ = request.query_params.get('range', '7d')
        if parse_relative(range_).days > 90:
            raise InvalidQuery('Reports cover at most 90 days.')
        fmt = request.query_params.get('format', 'json')
        if fmt not in ('json', 'csv', 'pdf'):
            raise InvalidQuery('format must be json, csv or pdf.')
        if fmt != 'json' and not has_role(request.user, ROLE_ANALYST):
            raise PermissionDenied('Exporting reports requires the analyst role or higher.')
        org = request.user.organization
        report = generator(org, range_)
        if fmt == 'json':
            return Response({**report, 'range': range_, 'generated_at': timezone.now()})
        record_audit(request, 'export', target_type='report', target_repr=f'{key} ({fmt})', changes={'range': range_})
        name = f'loghub-{key}-{timezone.now():%Y%m%d}.{fmt}'
        if fmt == 'csv':
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(report['columns'])
            for row in report['rows']:
                writer.writerow([("'" + v) if isinstance(v, str) and v[:1] in ('=', '+', '-', '@') else v for v in row])
            resp = HttpResponse(buf.getvalue(), content_type='text/csv')
        else:
            resp = HttpResponse(_pdf(report, org, range_), content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="{name}"'
        return resp
