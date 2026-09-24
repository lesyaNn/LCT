'use client';

import { toPng } from 'html-to-image';
import { formatDateTimeRu } from '@/shared/lib/formatters';

export type ChartExportFormat = 'png' | 'pdf';

const EXPORT_WIDTH = 960;
const EXPORT_PIXEL_RATIO = 2;

function nextPaint(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
}

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
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('en-US')
    .replace(/[^a-z0-9]+/g, '-')
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

  const parent = target.parentNode;
  if (!parent) throw new Error('Область графика не найдена.');

  const nextSibling = target.nextSibling;
  const originalStyle = target.style.cssText;
  const originalExporting = target.dataset.chartExporting;
  const targetRect = target.getBoundingClientRect();
  const placeholder = target.cloneNode(true) as HTMLElement;
  placeholder.setAttribute('aria-hidden', 'true');
  placeholder.setAttribute('inert', '');
  placeholder.style.width = `${targetRect.width}px`;
  placeholder.style.height = `${targetRect.height}px`;
  placeholder.style.pointerEvents = 'none';
  parent.insertBefore(placeholder, target);

  const rootStyles = getComputedStyle(document.documentElement);
  const surface = resolveColor(rootStyles.getPropertyValue('--rtk-color-surface').trim() || 'white');
  const textSecondary = resolveColor(rootStyles.getPropertyValue('--rtk-color-text-secondary').trim() || 'black');
  const border = resolveColor(rootStyles.getPropertyValue('--rtk-color-border').trim() || 'transparent');
  const wrapper = document.createElement('div');
  wrapper.setAttribute('aria-hidden', 'true');
  Object.assign(wrapper.style, {
    background: surface,
    boxSizing: 'border-box',
    color: getComputedStyle(document.body).color,
    fontFamily: getComputedStyle(document.body).fontFamily,
    left: '-100000px',
    position: 'fixed',
    top: '0',
    width: `${EXPORT_WIDTH}px`,
    zIndex: '-1',
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

  document.body.append(wrapper);
  wrapper.append(target, footer);
  target.dataset.chartExporting = 'true';
  Object.assign(target.style, {
    boxSizing: 'border-box',
    flex: 'none',
    margin: '0',
    maxWidth: 'none',
    width: `${EXPORT_WIDTH}px`,
  });

  let restoreSvgPaints: (() => void) | undefined;
  try {
    restoreSvgPaints = resolveSvgPaints(target);
    await nextPaint();
    return await toPng(wrapper, {
      backgroundColor: surface,
      cacheBust: true,
      filter: (node) => !(node instanceof HTMLElement && node.hasAttribute('data-chart-export-ui')),
      pixelRatio: EXPORT_PIXEL_RATIO,
      width: EXPORT_WIDTH,
    });
  } finally {
    restoreSvgPaints?.();
    if (nextSibling && nextSibling.parentNode === parent) parent.insertBefore(target, nextSibling);
    else parent.appendChild(target);
    target.style.cssText = originalStyle;
    if (originalExporting === undefined) delete target.dataset.chartExporting;
    else target.dataset.chartExporting = originalExporting;
    placeholder.remove();
    wrapper.remove();
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
