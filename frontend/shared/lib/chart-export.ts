'use client';

import { toPng } from 'html-to-image';
import { formatDateTimeRu } from '@/shared/lib/formatters';

export type ChartExportFormat = 'png' | 'pdf';

const EXPORT_PIXEL_RATIO = 2;

function resolveColor(value: string): string {
  const probe = document.createElement('span');
  probe.style.color = value;
  probe.style.position = 'fixed';
  probe.style.visibility = 'hidden';
  document.body.append(probe);
  const color = getComputedStyle(probe).color;
  probe.remove();
  return color;
}

function safeFilenameSlug(value: string): string {
  const slug = value
    .normalize('NFC')
    .toLocaleLowerCase('ru-RU')
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
  return slug || 'chart';
}

function downloadDataUrl(dataUrl: string, filename: string): void {
  const link = document.createElement('a');
  link.download = filename;
  link.href = dataUrl;
  link.rel = 'noopener';
  document.body.append(link);
  link.click();
  link.remove();
}

function resolveSvgPaints(target: HTMLElement): () => void {
  const changes: Array<{ element: SVGElement; attribute: string; value: string }> = [];
  const paintAttributes = ['fill', 'stroke', 'stop-color', 'flood-color', 'color'];

  target.querySelectorAll('svg *').forEach((node) => {
    if (!(node instanceof SVGElement)) return;
    const computed = getComputedStyle(node);
    paintAttributes.forEach((attribute) => {
      const value = node.getAttribute(attribute);
      if (!value?.includes('var(')) return;
      const property = attribute === 'stop-color' ? 'stopColor' : attribute;
      const resolved = computed.getPropertyValue(attribute) || (computed as unknown as Record<string, string>)[property];
      if (!resolved) return;
      changes.push({ element: node, attribute, value });
      node.setAttribute(attribute, resolved);
    });
  });

  return () => changes.forEach(({ element, attribute, value }) => element.setAttribute(attribute, value));
}

async function renderChartComposition(target: HTMLElement): Promise<string> {
  await document.fonts?.ready;
  const targetRect = target.getBoundingClientRect();
  if (!targetRect.width || !targetRect.height) throw new Error('Область графика не видна.');
  // Capture the rendered SVG without moving the live React/Recharts tree.
  // Moving it changes ResponsiveContainer's measured width and can blank the chart.
  const clone = target.cloneNode(true) as HTMLElement;
  clone.setAttribute('aria-hidden', 'true');
  clone.dataset.chartExporting = 'true';
  clone.style.width = `${targetRect.width}px`;
  clone.style.height = `${targetRect.height}px`;
  clone.style.flex = 'none';

  const rootStyles = getComputedStyle(document.documentElement);
  const surface = resolveColor(rootStyles.getPropertyValue('--rtk-color-surface').trim() || 'white');
  const textSecondary = resolveColor(rootStyles.getPropertyValue('--rtk-color-text-secondary').trim() || 'black');
  const border = resolveColor(rootStyles.getPropertyValue('--rtk-color-border').trim() || 'transparent');
  const host = document.createElement('div');
  Object.assign(host.style, {
    left: '-100000px',
    position: 'fixed',
    top: '0',
    width: `${targetRect.width}px`,
    zIndex: '-1',
  });
  const wrapper = document.createElement('div');
  wrapper.setAttribute('aria-hidden', 'true');
  Object.assign(wrapper.style, {
    background: surface,
    boxSizing: 'border-box',
    color: getComputedStyle(document.body).color,
    fontFamily: getComputedStyle(document.body).fontFamily,
    width: `${targetRect.width}px`,
  });

  const footer = document.createElement('footer');
  footer.textContent = `Сформировано: ${formatDateTimeRu(new Date().toISOString())}`;
  Object.assign(footer.style, {
    borderTop: `1px solid ${border}`,
    color: textSecondary,
    fontSize: '12px',
    lineHeight: '20px',
    margin: '0 20px',
    padding: '12px 0 16px',
    textAlign: 'right',
  });

  document.body.append(host);
  host.append(wrapper);
  wrapper.append(clone, footer);

  let restoreSvgPaints: (() => void) | undefined;
  try {
    restoreSvgPaints = resolveSvgPaints(clone);
    return await toPng(wrapper, {
      backgroundColor: surface,
      cacheBust: true,
      filter: (node) => !(node instanceof HTMLElement && node.hasAttribute('data-chart-export-ui')),
      pixelRatio: Math.max(EXPORT_PIXEL_RATIO, Math.ceil(1200 / targetRect.width)),
      width: targetRect.width,
    });
  } finally {
    restoreSvgPaints?.();
    host.remove();
  }
}

async function imageDimensions(dataUrl: string): Promise<{ width: number; height: number }> {
  const image = new Image();
  image.src = dataUrl;
  await image.decode();
  return { width: image.naturalWidth, height: image.naturalHeight };
}

export async function exportChart(
  target: HTMLElement,
  format: ChartExportFormat,
  filenameSlug: string,
): Promise<void> {
  const png = await renderChartComposition(target);
  const filename = `${safeFilenameSlug(filenameSlug)}-${new Date().toISOString().slice(0, 10)}`;

  if (format === 'png') {
    downloadDataUrl(png, `${filename}.png`);
    return;
  }

  const [{ jsPDF }, dimensions] = await Promise.all([import('jspdf'), imageDimensions(png)]);
  const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4', compress: true });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = 10;
  const availableWidth = pageWidth - margin * 2;
  const availableHeight = pageHeight - margin * 2;
  const scale = Math.min(availableWidth / dimensions.width, availableHeight / dimensions.height);
  const width = dimensions.width * scale;
  const height = dimensions.height * scale;
  pdf.addImage(png, 'PNG', (pageWidth - width) / 2, (pageHeight - height) / 2, width, height, undefined, 'FAST');
  pdf.save(`${filename}.pdf`);
}
