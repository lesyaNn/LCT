'use client';

import Search from '@atomaro/icons/24/action/Search';
import Edit from '@atomaro/icons/24/editor/Edit';
import Link from 'next/link';
import Image from 'next/image';
import { useMemo, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';
import { EmptyState } from '@/shared/ui/empty-state';
import { Drawer } from '@/shared/ui/rtk/drawer';
import { IconButton } from '@/shared/ui/rtk/icon-button';
import { Input } from '@/shared/ui/rtk/form-controls';
import type { DocsArticle, DocsSection, DocsSnapshot } from '@/shared/lib/docs-repository';
import styles from './docs-page.module.css';

interface DocsPageProps {
  docs: DocsSnapshot;
  initialArticleId?: string;
}

function plainTextFromMarkdown(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/[*_`>|~]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function articleSearchText(article: DocsArticle): string {
  return `${article.title} ${article.sectionTitle} ${plainTextFromMarkdown(article.content)}`.toLocaleLowerCase('ru-RU');
}

function searchFragment(article: DocsArticle, query: string): string {
  const plain = plainTextFromMarkdown(article.content);
  const position = plain.toLocaleLowerCase('ru-RU').indexOf(query);
  const start = Math.max(0, position - 45);
  return `${start ? '…' : ''}${plain.slice(start, start + 105)}${start + 105 < plain.length ? '…' : ''}`;
}

function DocsNavigation({ sections, activeArticleId, query, onQueryChange, onNavigate }: { sections: DocsSection[]; activeArticleId?: string; query: string; onQueryChange: (value: string) => void; onNavigate?: () => void }) {
  const articles = sections.flatMap((section) => section.articles);
  const normalizedQuery = query.trim().toLocaleLowerCase('ru-RU');
  const results = normalizedQuery ? articles.filter((article) => articleSearchText(article).includes(normalizedQuery))
    .sort((left, right) => Number(right.title.toLocaleLowerCase('ru-RU').includes(normalizedQuery)) - Number(left.title.toLocaleLowerCase('ru-RU').includes(normalizedQuery)))
    .slice(0, 12) : [];
  return <>
    <label className={styles.searchField}><Search size={18} fill="currentColor" aria-hidden="true" /><span className={styles.visuallyHidden}>Поиск по документации</span><Input type="search" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Поиск по документации" aria-label="Поиск по документации" /></label>
    {normalizedQuery ? <div className={styles.searchResults} aria-label="Результаты поиска">{results.length ? results.map((article) => <Link className={styles.searchResult} href={article.href} key={article.id} onClick={onNavigate}><strong>{article.title}</strong><span>{searchFragment(article, normalizedQuery)}</span></Link>) : <EmptyState icon={<Search size={18} fill="currentColor" />} title="Ничего не найдено" description="Попробуйте изменить поисковый запрос." headingLevel={3} />}</div> : null}
    <nav className={styles.docsNav} aria-label="Навигация по документации">
      <Link className={`${styles.homeLink} ${!activeArticleId ? styles.activeArticle : ''}`} href="/docs" onClick={onNavigate}>Справочный центр</Link>
      {sections.filter((section) => section.articles.length).map((section) => {
        const active = section.articles.some((article) => article.id === activeArticleId);
        return <details className={styles.navSection} key={`${section.id}-${activeArticleId ?? 'home'}`} open={active || (!activeArticleId && section.id === 'user-guide')}>
          <summary>{section.title}</summary>
          <ul>{section.articles.map((article) => <li key={article.id}><Link className={activeArticleId === article.id ? styles.activeArticle : undefined} href={article.href} onClick={onNavigate} aria-current={activeArticleId === article.id ? 'page' : undefined}>{article.title}</Link></li>)}</ul>
        </details>;
      })}
    </nav>
  </>;
}

const imageDimensions: Record<string, [number, number]> = {
  'docs-api-errors.jpg': [2730, 1420],
  'docs-api-main.jpg': [2730, 1250],
  'docs-api-method-detail.jpg': [2730, 1580],
  'docs-api-methods.jpg': [2730, 1450],
  'docs-assistant.jpg': [1830, 1510],
  'docs-audit.jpg': [2730, 630],
  'docs-catalogs-program-form.jpg': [1820, 1030],
  'docs-catalogs-programs.jpg': [2730, 1200],
  'docs-catalogs-university-form.jpg': [1820, 810],
  'docs-catalogs.jpg': [2730, 1280],
  'docs-dashboard-distribution.jpg': [2720, 1240],
  'docs-dashboard-funnel.jpg': [2720, 1250],
  'docs-dashboard-matrix.jpg': [2720, 1210],
  'docs-dashboard-priorities.jpg': [1370, 690],
  'docs-dashboard-trends.jpg': [2720, 840],
  'docs-dashboard.jpg': [2730, 1450],
  'docs-health-reasons.jpg': [2730, 1500],
  'docs-health-score.jpg': [2730, 1340],
  'docs-import.jpg': [2730, 1325],
  'docs-license-actions.jpg': [2670, 945],
  'docs-license-preview.jpg': [1480, 1600],
  'docs-license-ready.jpg': [2670, 945],
  'docs-notes-editor.jpg': [2730, 1420],
  'docs-notes-list.jpg': [2730, 1400],
  'docs-notifications-popover.jpg': [940, 455],
  'docs-notifications.jpg': [2730, 885],
  'docs-passport-documents.jpg': [2730, 940],
  'docs-passport-licenses.jpg': [2730, 930],
  'docs-passport-overview.jpg': [2730, 1360],
  'docs-passport-products.jpg': [2730, 920],
  'docs-reports-form.jpg': [2730, 1470],
  'docs-reports-preview.jpg': [2280, 1700],
  'docs-reports-statistics.jpg': [2280, 1700],
  'docs-system-search.jpg': [830, 1180],
  'docs-toast.jpg': [1050, 320],
  'docs-universities-cards.jpg': [2730, 1520],
  'docs-universities-map.jpg': [2730, 1530],
  'docs-universities-region.jpg': [2730, 1270],
  'docs-universities-table.jpg': [2730, 1470],
  'docs-users-graph.jpg': [2730, 1400],
  'docs-users-list.jpg': [2730, 1110],
  'docs-workflow-comments.jpg': [1650, 1420],
  'docs-workflow-default-tasks.jpg': [1870, 1170],
  'docs-workflow-detail-top.jpg': [2730, 1500],
  'docs-workflow-kanban.jpg': [2730, 1570],
  'docs-workflow-list.jpg': [2730, 1480],
  'docs-workflow-open-question.jpg': [1650, 1360],
  'docs-workflow-preview.jpg': [1520, 1050],
  'docs-workflow-template-editor.jpg': [2730, 1610],
  'docs-workflow-templates-list.jpg': [2730, 1090],
};

const markdownComponents: Components = {
  code: ({ children, ...props }) => String(children).trim() === ':edit:'
    ? <span className={styles.inlineIcon} role="img" aria-label="Редактировать"><Edit size={18} fill="currentColor" /></span>
    : <code {...props}>{children}</code>,
  a: ({ href, children, ...props }) => {
    if (href?.startsWith('/')) return <Link href={href} {...props}>{children}</Link>;
    return <a href={href} target={href?.startsWith('#') ? undefined : '_blank'} rel={href?.startsWith('#') ? undefined : 'noopener noreferrer'} {...props}>{children}</a>;
  },
  table: ({ children, ...props }) => <div className={styles.tableWrap}><table {...props}>{children}</table></div>,
  pre: ({ children, ...props }) => <pre className={styles.codeBlock} {...props}>{children}</pre>,
  img: ({ src, alt }) => {
    if (!src || typeof src !== 'string' || !src.startsWith('/docs/images/')) return null;
    const [width, height] = imageDimensions[src.split('/').at(-1) ?? ''] ?? [1200, 760];
    return <span className={styles.figure} role="figure" aria-label={alt ?? ''}><a href={src} target="_blank" rel="noopener noreferrer" aria-label={`Открыть изображение в полном размере: ${alt ?? 'скриншот'}`}><Image src={src} alt={alt ?? ''} width={width} height={height} sizes="(max-width: 768px) 100vw, (max-width: 1200px) 80vw, 900px" loading="lazy" /></a><span className={styles.caption}>{alt}</span></span>;
  },
};

function ArticleContent({ article }: { article: DocsArticle }) {
  const faq = article.id === 'help/faq' ? article.content.split(/^### /m).slice(1).map((entry) => { const [question, ...answer] = entry.split('\n'); return { question: question.trim(), answer: answer.join('\n').trim() }; }) : [];
  return <article className={styles.article} aria-labelledby="docs-article-title"><header className={styles.articleHeader}><p className={styles.articleSection}>{article.sectionTitle}</p><h1 id="docs-article-title">{article.title}</h1></header><div className={styles.markdown}>{article.id === 'help/faq' ? <div className={styles.faqList}>{faq.map(({ question, answer }) => <details className={styles.faqItem} key={question}><summary>{question}</summary><div><ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown></div></details>)}</div> : <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>{article.content}</ReactMarkdown>}</div></article>;
}

function DocsLanding({ docs }: { docs: DocsSnapshot }) {
  const cards = [
    ['user-guide/getting-started', 'Начало работы', 'Основные возможности CRM и первые действия.'],
    ['user-guide/universities', 'Работа с вузами', 'Паспорт, программы, продукты и ответственные.'],
    ['user-guide/workflow', 'Workflow', 'Этапы, комментарии, файлы и задачи.'],
    ['user-guide/notifications', 'Уведомления', 'События, которые требуют внимания.'],
    ['user-guide/reports', 'Отчёты', 'Фильтрация, формирование и выгрузка.'],
  ];
  return <div className={styles.landing}><p className={styles.eyebrow}>Помощь по CRM</p><h1>Справочный центр CRM</h1><p>Здесь собраны инструкции по работе с системой: поиск вуза, паспорт, Workflow, уведомления и отчёты. Разделы для руководителя и администратора находятся в навигации.</p><div className={styles.landingCards}>{cards.map(([id, title, description]) => { const article = docs.articles.find((item) => item.id === id); return article ? <Link href={article.href} key={id}><strong>{title}</strong><span>{description}</span></Link> : null; })}</div></div>;
}

export function DocsPage({ docs, initialArticleId }: DocsPageProps) {
  const [query, setQuery] = useState('');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const article = initialArticleId ? docs.articles.find((item) => item.id === initialArticleId) : undefined;
  const invalidArticle = Boolean(initialArticleId && !article);
  const selectedArticleId = article?.id;
  const mobileNavigation = useMemo(() => <DocsNavigation sections={docs.sections} activeArticleId={selectedArticleId} query={query} onQueryChange={setQuery} onNavigate={() => setMobileNavOpen(false)} />, [docs.sections, query, selectedArticleId]);

  return <section className={styles.docsShell}>
    <div className={styles.mobileToolbar}><strong>Навигация по документации</strong><IconButton icon="menu" label="Открыть навигацию по документации" aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen(true)} /></div>
    <aside className={styles.sidebar}><DocsNavigation sections={docs.sections} activeArticleId={selectedArticleId} query={query} onQueryChange={setQuery} /></aside>
    {mobileNavOpen ? <Drawer title="Документация" onClose={() => setMobileNavOpen(false)}>{mobileNavigation}</Drawer> : null}
    <main className={styles.content}>{article ? <ArticleContent article={article} /> : invalidArticle ? <EmptyState presentation="large" title="Статья не найдена" description="Проверьте ссылку или выберите материал в навигации." /> : <DocsLanding docs={docs} />}</main>
  </section>;
}
