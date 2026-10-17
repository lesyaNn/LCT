'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Chat from '@atomaro/icons/24/communication/Chat';
import Send from '@atomaro/icons/24/action/Send';
import { Avatar } from '@/shared/ui/rtk/avatar';
import { Button } from '@/shared/ui/rtk/button';
import { Icon } from '@/shared/ui/rtk/icon';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { TextArea } from '@/shared/ui/rtk/form-controls';
import type { AuthUser } from '@/shared/types/user';
import type { AssistantSource } from '@/shared/lib/assistant-repository';
import { useAssistantChat, type ChatMessage } from './use-assistant-chat';
import styles from './assistant-widget.module.css';

const robot = '/images/rostelecom_robot_flat.svg';
const quickQuestions = ['Как выгрузить отчёт?', 'Что означает статус?', 'Где просроченные этапы?', 'Как добавить вуз?'];

function supportedHref(href: string | undefined): string | null {
  if (!href) return null;
  if (/^\/(dashboard|universities|workflows|reports|audit|admin|docs)(\/|\?|$)/.test(href)) return href;
  try {
    const url = new URL(href);
    if (url.protocol === 'https:' || url.protocol === 'http:') return url.href;
  } catch { /* A relative or unsupported URL is not a link. */ }
  return null;
}

function SourceLinks({ sources }: { sources: AssistantSource[] }) {
  const valid = sources.filter((source) => source.url.startsWith('/docs?') || source.url === '/docs');
  if (!valid.length) return null;
  return <div className={styles.sources} aria-label="Источники ответа">{valid.map((source) =>
    <Link key={source.id} href={source.url} className={styles.sourceLink}>
      <Icon name="docs" size={19} /><span>Открыть: {source.title}</span><Icon name="chevron-right" size={18} />
    </Link>)}</div>;
}

function MarkdownAnswer({ text }: { text: string }) {
  return <div className={styles.answer}><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ href, children }) => {
      const safe = supportedHref(href);
      if (!safe) return <span>{children}</span>;
      if (safe.startsWith('/')) return <Link href={safe}>{children}</Link>;
      return <a href={safe} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
  }}>{text}</ReactMarkdown></div>;
}

function Message({ message, user, onRetry, sending }: { message: ChatMessage; user: AuthUser; onRetry: (message: ChatMessage) => void; sending: boolean }) {
  const isUser = message.role === 'user';
  const time = new Date(message.createdAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  return <div className={`${styles.messageRow} ${isUser ? styles.userRow : ''}`}>
    <div className={styles.messageAvatar}>{isUser ? <Avatar initials={user.initials} size="m" /> : <Image src={robot} alt="" width={43} height={43} />}</div>
    <div className={`${styles.bubble} ${isUser ? styles.userBubble : styles.assistantBubble}`}>
      {isUser ? <p className={styles.userText}>{message.text}</p> : <><MarkdownAnswer text={message.text} />{message.sources && <SourceLinks sources={message.sources} />}</>}
      <time className={styles.time} dateTime={message.createdAt}>{time}</time>
      {message.error && <div className={styles.messageError} role="alert"><span>{message.error}</span><Button type="button" variant="ghost" size="s" disabled={sending} onClick={() => onRetry(message)}>Повторить</Button></div>}
    </div>
  </div>;
}

export function AssistantWidget({ user, pathname, open, onOpen, onClose }: { user: AuthUser; pathname: string; open: boolean; onOpen: () => void; onClose: () => void }) {
  const [input, setInput] = useState('');
  const [showHint, setShowHint] = useState(false);
  const [showLauncher, setShowLauncher] = useState(false);
  const { messages, restoring, restoreError, sending, sendMessage, retry, retryRestore } = useAssistantChat(user.id, pathname);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const hintKey = `crm-ai-assistant-hint:v1:${user.id}`;
  const launcherKey = `crm-ai-assistant-launcher-hidden:v1:${user.id}`;

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      try {
        setShowHint(window.localStorage.getItem(hintKey) !== 'seen');
        setShowLauncher(window.localStorage.getItem(launcherKey) !== 'hidden');
      } catch { setShowHint(true); setShowLauncher(true); }
    });
    return () => cancelAnimationFrame(frame);
  }, [hintKey, launcherKey]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      setShowHint(false);
      try { window.localStorage.setItem(hintKey, 'seen'); } catch { /* Keep the current session dismissed. */ }
    });
    return () => cancelAnimationFrame(frame);
  }, [open, hintKey]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }));
  }, [open, messages.length, sending]);

  useEffect(() => {
    const viewport = window.visualViewport;
    const update = () => {
      const visibleHeight = viewport?.height ?? window.innerHeight;
      const covered = Math.max(0, window.innerHeight - visibleHeight - (viewport?.offsetTop ?? 0));
      rootRef.current?.style.setProperty('--assistant-visible-height', `${visibleHeight}px`);
      rootRef.current?.style.setProperty('--assistant-keyboard-inset', `${covered}px`);
    };
    update();
    viewport?.addEventListener('resize', update);
    viewport?.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    return () => {
      viewport?.removeEventListener('resize', update);
      viewport?.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, []);

  function dismissHint() {
    setShowHint(false);
    try { window.localStorage.setItem(hintKey, 'seen'); } catch { /* Keep the current session dismissed. */ }
  }

  function openChat() {
    dismissHint();
    onOpen();
  }

  function dismissLauncher() {
    setShowLauncher(false);
    dismissHint();
    try { window.localStorage.setItem(launcherKey, 'hidden'); } catch { /* Keep the current session dismissed. */ }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sendMessage(input)) setInput('');
  }

  return <div ref={rootRef} className={styles.root}>
    {!open && showLauncher && <div className={styles.closed}>
      {showHint && <div className={styles.hint} role="status">
        <Image src={robot} alt="" width={58} height={58} />
        <button className={styles.hintContent} type="button" onClick={openChat}><strong>Есть вопросы?</strong><span>Спросите ИИ-помощника</span></button>
        <IconButton icon="close" label="Закрыть подсказку" size={16} className={styles.hintClose} onClick={dismissHint} />
      </div>}
      <span className={styles.launcherWrap}>
        <IconButton icon="close" label="Скрыть плавающую кнопку ИИ-помощника" size={14} className={styles.launcherClose} onClick={dismissLauncher} />
        <button type="button" className={styles.launcher} aria-label="Открыть ИИ-помощника" aria-expanded={false} onClick={openChat}><Chat size={28} fill="currentColor" /></button>
      </span>
    </div>}

    {open && <section className={styles.panel} role="dialog" aria-modal="false" aria-labelledby="assistant-title">
      <header className={styles.header}>
        <Image src={robot} alt="" width={66} height={66} className={styles.headerRobot} />
        <div className={styles.headerTitle}><h2 id="assistant-title">ИИ-помощник</h2><p>Ваш верный помощник</p></div>
        <IconButton icon="close" label="Закрыть ИИ-помощника" className={styles.panelClose} onClick={onClose} />
      </header>

      <div ref={scrollRef} className={styles.scroll} aria-live="polite">
        <div className={styles.messageRow}>
          <div className={styles.messageAvatar}><Image src={robot} alt="" width={43} height={43} /></div>
          <div className={`${styles.bubble} ${styles.assistantBubble} ${styles.greeting}`}><p>Здравствуйте! 👋<br />Я ваш помощник системы ИТ Школа Ростелекома. Могу подсказать, как работать с разделами, помочь найти нужные данные и ответить на вопросы по отчётам, статусам и настройкам.</p></div>
        </div>
        <div className={styles.quickQuestions} aria-label="Быстрые вопросы">{quickQuestions.map((question) => <Button key={question} type="button" variant="secondary" className={styles.quickButton} disabled={sending || restoring} onClick={() => sendMessage(question)}>{question}<Icon name="chevron-right" size={17} /></Button>)}</div>
        {restoring && <p className={styles.info} role="status">Загружаем диалог…</p>}
        {restoreError && <div className={styles.restoreError} role="alert"><span>Не удалось загрузить предыдущий диалог: {restoreError}</span><Button type="button" variant="ghost" size="s" disabled={sending} onClick={retryRestore}>Повторить</Button></div>}
        {messages.map((message) => <Message key={message.id} message={message} user={user} onRetry={retry} sending={sending} />)}
        {sending && <p className={styles.info} role="status">Помощник печатает<span className={styles.dots}>…</span></p>}
      </div>

      <form className={styles.composer} onSubmit={submit}>
        <TextArea ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
        }} placeholder="Напишите вопрос..." aria-label="Напишите вопрос" maxLength={2000} rows={1} className={styles.input} disabled={restoring} />
        <Button type="submit" variant="primary" className={styles.sendButton} aria-label="Отправить вопрос" disabled={!input.trim() || sending || restoring}><Send size={23} fill="currentColor" /></Button>
      </form>
    </section>}
  </div>;
}
