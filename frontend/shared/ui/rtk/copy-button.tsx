'use client';

import { useEffect, useRef, useState } from 'react';
import Copy from '@atomaro/icons/24/action/Copy';
import { IconButton } from './icon-button';
import { Toast } from './toast';

export function CopyButton({ value, label, className }: { value: string; label: string; className?: string }) {
  const [feedback, setFeedback] = useState<'success' | 'error' | null>(null);
  const [pending, setPending] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!feedback) return;
    const timeout = setTimeout(() => setFeedback(null), 4000);
    return () => clearTimeout(timeout);
  }, [feedback]);
  async function copy() {
    setPending(true);
    setFeedback(null);
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(value);
      if (mounted.current) setFeedback('success');
    } catch {
      if (mounted.current) setFeedback('error');
    } finally {
      if (mounted.current) setPending(false);
    }
  }
  return <>
    <IconButton className={className} label={label} icon={<Copy size={16} fill="currentColor" />} disabled={pending || !value.trim()} onClick={() => void copy()} />
    {feedback ? <Toast intent={feedback} title={feedback === 'success' ? 'Скопировано' : 'Не удалось скопировать'} message={feedback === 'error' ? 'Браузер запретил доступ к буферу. Откройте сайт по HTTPS или выделите и скопируйте текст вручную.' : undefined} onClose={() => setFeedback(null)} /> : null}
  </>;
}
