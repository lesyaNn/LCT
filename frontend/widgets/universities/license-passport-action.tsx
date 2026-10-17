'use client';

import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ChevronDown from '@atomaro/icons/24/navigation/ChevronDown';
import Download from '@atomaro/icons/24/action/Download';
import Refresh from '@atomaro/icons/24/action/Refresh';
import PasswordShow from '@atomaro/icons/24/action/PasswordShow';
import { useAuth } from '@/shared/auth/AuthProvider';
import { hasPermission } from '@/shared/lib/access-control';
import { isMockDataSourceFor } from '@/shared/lib/data-source';
import { normalizeApiError } from '@/shared/lib/api-errors';
import { downloadLicensePassport } from '@/shared/lib/license-passports';
import type { UniversityLicenseRow } from '@/shared/lib/universities-repository';
import { Button, ButtonAnchor } from '@/shared/ui/rtk/button';
import { Modal } from '@/shared/ui/rtk/modal';
import styles from './license-passport.module.css';

export function LicensePassportAction({ universityId, license }: { universityId: string; license: UniversityLicenseRow }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const focusLast = useRef(false);
  const request = useRef<AbortController | null>(null);
  const errorId = useId();
  const menuId = useId();
  useEffect(() => () => { request.current?.abort(); }, []);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  const trigger = () => rootRef.current?.querySelector<HTMLButtonElement>('[aria-haspopup="menu"]');
  const closeMenu = () => { setMenuOpen(false); trigger()?.focus(); };

  useLayoutEffect(() => {
    if (!menuOpen) return;
    const position = () => {
      const anchor = trigger()?.getBoundingClientRect();
      const menu = menuRef.current;
      if (!anchor || !menu) return;
      const { width, height } = menu.getBoundingClientRect();
      menu.style.left = `${Math.max(12, Math.min(anchor.right - width, window.innerWidth - width - 12))}px`;
      const below = anchor.bottom + 8;
      menu.style.top = `${Math.max(12, below + height <= window.innerHeight - 12 ? below : anchor.top - height - 8)}px`;
    };
    position();
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    return () => { window.removeEventListener('resize', position); window.removeEventListener('scroll', position, true); };
  }, [menuOpen, url, error]);

  useEffect(() => {
    if (!menuOpen) return;
    const items = menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)');
    if (items?.length) items[focusLast.current ? items.length - 1 : 0].focus();
    else menuRef.current?.focus();
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node) && !menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [menuOpen]);

  if (isMockDataSourceFor('passport') || !hasPermission(user, 'university.read')) return null;

  const missing = [
    !license.product?.trim() && 'наименование ПО',
    !license.licenseNumber?.trim() && 'номер лицензии',
    !license.signedAt && 'дата начала действия',
    !license.expiresAt && 'дата окончания действия',
    (!license.contract?.trim() || license.contract === '—') && 'связанный договор',
  ].filter(Boolean);

  async function generate() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setMenuOpen(false);
    setLoading(true);
    setError(null);
    setUrl(null);
    setPreview(false);
    try {
      const blob = await downloadLicensePassport(universityId, license.id, controller.signal);
      if (!controller.signal.aborted) setUrl(URL.createObjectURL(blob));
    } catch (cause) {
      if (!controller.signal.aborted) {
        const normalized = normalizeApiError(cause);
        const fields = normalized.details.missing_fields;
        setError(Array.isArray(fields) && fields.every((field) => typeof field === 'string')
          ? `Заполните или исправьте: ${fields.join('; ')}.`
          : normalized.message);
      }
    } finally {
      request.current = null;
      if (!controller.signal.aborted) {
        setLoading(false);
        focusLast.current = false;
        setMenuOpen(true);
      }
    }
  }

  return <div className={styles.action} ref={rootRef}>
    <Button type="button" size="s" variant="secondary" className={styles.trigger} loading={loading} disabled={loading}
      aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuOpen ? menuId : undefined}
      onClick={() => { focusLast.current = false; setMenuOpen((open) => !open); }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault(); focusLast.current = event.key === 'ArrowUp'; setMenuOpen(true);
        }
      }}>
      {loading ? 'Формирование…' : 'Действия'}
      {!loading ? <ChevronDown size={16} fill="currentColor" aria-hidden="true" className={menuOpen ? styles.chevronOpen : undefined} /> : null}
    </Button>
    {menuOpen ? createPortal(<div className={styles.menu} ref={menuRef} tabIndex={-1} onKeyDown={(event) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeMenu(); }
      if (event.key === 'Tab') closeMenu();
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? []);
        if (!items.length) return;
        const current = items.indexOf(document.activeElement as HTMLElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
          : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[next].focus();
      }
    }}>
      <div role="menu" id={menuId} aria-label={`Паспорт лицензии ${license.licenseNumber}`}>
        {url ? <>
          <button type="button" role="menuitem" className={styles.menuItem} onClick={() => { closeMenu(); setPreview(true); }}>
            <PasswordShow size={20} fill="currentColor" aria-hidden="true" />Открыть PDF
          </button>
          <a role="menuitem" className={styles.menuItem} href={url} download={`license-passport-${license.id}.pdf`} onClick={closeMenu}>
            <Download size={20} fill="currentColor" aria-hidden="true" />Скачать PDF
          </a>
        </> : null}
        <button type="button" role="menuitem" className={styles.menuItem} disabled={missing.length > 0}
          aria-describedby={missing.length || error ? errorId : undefined} onClick={() => void generate()}>
          <Refresh size={20} fill="currentColor" aria-hidden="true" />{url ? 'Сформировать заново' : 'Сформировать паспорт лицензии'}
        </button>
      </div>
      <div className={styles.menuFooter}>
        {missing.length ? <p id={errorId} className={styles.hint}>Заполните: {missing.join(', ')}.</p>
          : error ? <p id={errorId} className={styles.error} role="alert">{error}</p>
          : <p className={styles.hint}>{url ? 'Если данные изменились, сформируйте паспорт заново.' : 'Сформируйте паспорт, чтобы открыть или скачать PDF.'}</p>}
      </div>
    </div>, document.body) : null}
    {preview && url ? <Modal title="Паспорт лицензии" size="l" fullHeight onClose={() => setPreview(false)}>
      <div className={styles.preview}>
        <iframe title={`Паспорт лицензии ${license.licenseNumber}`} src={url} />
        <p className={styles.hint}>Если браузер не показывает PDF, скачайте документ для просмотра и печати.</p>
        <ButtonAnchor href={url} download={`license-passport-${license.id}.pdf`}>Скачать PDF</ButtonAnchor>
      </div>
    </Modal> : null}
  </div>;
}
