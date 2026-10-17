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
  const scrollArea = target.querySelector<HTMLElement>('[data-chart-scroll]');
  const cloneScrollArea = clone.querySelector<HTMLElement>('[data-chart-scroll]');
  if (scrollArea && cloneScrollArea) {
    clone.style.height = 'auto';
    clone.style.minHeight = `${targetRect.height}px`;
    cloneScrollArea.style.flex = 'none';
    cloneScrollArea.style.height = `${scrollArea.scrollHeight}px`;
    cloneScrollArea.style.overflow = 'visible';
  }

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

async function decodeImage(dataUrl: string): Promise<HTMLImageElement> {
  const image = new Image();
  image.src = dataUrl;
  await image.decode();
  return image;
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

  const [{ jsPDF }, image] = await Promise.all([import('jspdf'), decodeImage(png)]);
  const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4', compress: true });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = 10;
  const availableWidth = pageWidth - margin * 2;
  const availableHeight = pageHeight - margin * 2;
  const widthScale = availableWidth / image.naturalWidth;
  if (image.naturalHeight * widthScale <= availableHeight * 2) {
    const scale = Math.min(widthScale, availableHeight / image.naturalHeight);
    const width = image.naturalWidth * scale;
    const height = image.naturalHeight * scale;
    pdf.addImage(png, 'PNG', (pageWidth - width) / 2, (pageHeight - height) / 2, width, height, undefined, 'FAST');
  } else {
    const pixelsPerPage = Math.floor(availableHeight / widthScale);
    for (let top = 0; top < image.naturalHeight; top += pixelsPerPage) {
      const sliceHeight = Math.min(pixelsPerPage, image.naturalHeight - top);
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = sliceHeight;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Не удалось подготовить страницу PDF.');
      context.drawImage(image, 0, top, image.naturalWidth, sliceHeight, 0, 0, image.naturalWidth, sliceHeight);
      if (top) pdf.addPage();
      pdf.addImage(canvas.toDataURL('image/png'), 'PNG', margin, margin, availableWidth, sliceHeight * widthScale, undefined, 'FAST');
    }
  }
  pdf.save(`${filename}.pdf`);
}
