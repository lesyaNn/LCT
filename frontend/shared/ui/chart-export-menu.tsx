'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';
import Download from '@atomaro/icons/24/action/Download';
import ChevronDown from '@atomaro/icons/24/navigation/ChevronDown';
import DocumentImage from '@atomaro/icons/24/document/DocumentImage';
import DocumentText from '@atomaro/icons/24/document/DocumentText';
import { exportChart, type ChartExportFormat } from '@/shared/lib/chart-export';
import { Button } from '@/shared/ui/rtk/button';
import { Toast } from '@/shared/ui/rtk/toast';
import { Tooltip } from '@/shared/ui/rtk/tooltip';
import styles from './chart-export-menu.module.css';

interface ChartExportMenuProps {
  filenameSlug: string;
  targetRef: RefObject<HTMLElement | null>;
  testId: string;
}

export function ChartExportMenu({ filenameSlug, targetRef, testId }: ChartExportMenuProps) {
  const [open, setOpen] = useState(false);
  const [busyFormat, setBusyFormat] = useState<ChartExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const toggleMenu = () => {
    if (busyFormat) return;
    setOpen((value) => {
      if (!value) requestAnimationFrame(() => firstItemRef.current?.focus());
      return !value;
    });
  };

  const runExport = async (format: ChartExportFormat) => {
    const target = targetRef.current;
    if (!target || busyFormat) return;
    setOpen(false);
    setError(null);
    setBusyFormat(format);
    try {
      await exportChart(target, format, filenameSlug);
    } catch (cause) {
      console.error('Chart export failed', cause instanceof Error ? cause.name : 'unknown');
      setError('Попробуйте ещё раз. Если ошибка повторится, обновите страницу.');
    } finally {
      setBusyFormat(null);
    }
  };

  return (
    <div className={styles.root} data-chart-export-ui ref={rootRef}>
      <Tooltip content="Скачать график как PNG или PDF">
        <Button
          aria-expanded={open}
          aria-haspopup="menu"
          data-testid={testId}
          disabled={Boolean(busyFormat)}
          loading={Boolean(busyFormat)}
          size="s"
          type="button"
          variant="ghost"
          onClick={toggleMenu}
        >
          <Download size={16} fill="currentColor" aria-hidden="true" />
          <span className={styles.label}>{busyFormat ? 'Формируем' : 'Скачать'}</span>
          {!busyFormat ? <ChevronDown size={16} fill="currentColor" aria-hidden="true" /> : null}
        </Button>
      </Tooltip>
      {open ? (
        <div className={styles.menu} role="menu" aria-label="Формат скачивания">
          <button data-testid={`${testId}-png`} ref={firstItemRef} role="menuitem" type="button" onClick={() => void runExport('png')}>
            <DocumentImage size={18} fill="currentColor" aria-hidden="true" />
            <span><strong>PNG</strong><small>Изображение в высоком качестве</small></span>
          </button>
          <button data-testid={`${testId}-pdf`} role="menuitem" type="button" onClick={() => void runExport('pdf')}>
            <DocumentText size={18} fill="currentColor" aria-hidden="true" />
            <span><strong>PDF</strong><small>Готово для печати и отправки</small></span>
          </button>
        </div>
      ) : null}
      {error ? <div className={styles.toast}><Toast intent="error" title="График не скачан" message={error} onClose={() => setError(null)} /></div> : null}
    </div>
  );
}
