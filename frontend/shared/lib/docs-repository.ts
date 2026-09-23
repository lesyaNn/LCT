import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';

export interface DocsTopicDefinition {
  slug: string;
  title: string;
}

export interface DocsSection {
  id: string;
  title: string;
  topics: DocsTopicDefinition[];
  articles: DocsArticle[];
}

export interface DocsArticle {
  id: string;
  slug: string;
  title: string;
  sectionId: string;
  sectionTitle: string;
  content: string;
  headings: string[];
  href: string;
  order: number;
}

export interface DocsSnapshot {
  sections: DocsSection[];
  articles: DocsArticle[];
}

/** The four top-level sections are the stable content contract for P5 docs. */
export const DOC_SECTION_DEFINITIONS: Array<{ id: string; title: string; topics: DocsTopicDefinition[] }> = [
  {
    id: 'user-guide',
    title: 'Руководство пользователя',
    topics: [
      { slug: 'getting-started', title: 'Начало работы' },
      { slug: 'universities', title: 'Работа с ВУЗами' },
      { slug: 'workflow', title: 'Workflow' },
      { slug: 'documents', title: 'Загрузка документов' },
      { slug: 'reports', title: 'Отчёты' },
      { slug: 'health-score', title: 'Health Score' },
    ],
  },
  {
    id: 'admin-guide',
    title: 'Руководство администратора',
    topics: [
      { slug: 'users', title: 'Пользователи' },
      { slug: 'workflow-templates', title: 'Workflow-шаблоны' },
      { slug: 'catalogs', title: 'Каталоги' },
      { slug: 'roles', title: 'Роли и права' },
      { slug: 'import', title: 'Импорт' },
    ],
  },
  { id: 'faq', title: 'FAQ', topics: [] },
  { id: 'roles', title: 'Роли и права', topics: [] },
];

const contentRoots = [
  path.join(process.cwd(), 'public', 'docs'),
  path.join(process.cwd(), 'src', 'content', 'docs'),
];

function isRecord(value: unknown): value is Record<string, string> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function titleFromSlug(slug: string): string {
  return slug.replace(/[-_]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/\\/g, '/');
}

function parseFrontMatter(source: string): { metadata: Record<string, string>; body: string } {
  const match = source.match(/^---\s*\n([\s\S]*?)\n---\s*\n?/);
  if (!match) return { metadata: {}, body: source };
  const metadata: Record<string, string> = {};
  for (const line of match[1].split('\n')) {
    const item = line.match(/^([\w-]+):\s*(.*?)\s*$/);
    if (!item) continue;
    metadata[item[1]] = item[2].replace(/^['"]|['"]$/g, '');
  }
  return { metadata, body: source.slice(match[0].length) };
}

function headingsFromMarkdown(markdown: string): string[] {
  return Array.from(markdown.matchAll(/^#{1,6}\s+(.+?)\s*#*\s*$/gm), (match) => match[1].trim());
}

async function markdownFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(entries.map(async (entry) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return markdownFiles(fullPath);
    return entry.isFile() && entry.name.toLowerCase().endsWith('.md') ? [fullPath] : [];
  }));
  return files.flat();
}

function sectionForFile(relativeFile: string, metadata: Record<string, string>) {
  const pathParts = relativeFile.split('/');
  const requested = normalize(metadata.section ?? pathParts[0]?.replace(/\.md$/i, '') ?? '');
  return DOC_SECTION_DEFINITIONS.find((section) => section.id === requested) ?? DOC_SECTION_DEFINITIONS[0];
}

function articleFromSource(root: string, filePath: string, source: string): DocsArticle {
  const relativeFile = path.relative(root, filePath).split(path.sep).join('/');
  const { metadata, body } = parseFrontMatter(source);
  const section = sectionForFile(relativeFile, metadata);
  const relativeSlug = relativeFile.replace(/\.md$/i, '');
  const slug = normalize(metadata.slug ?? (relativeSlug.split('/').slice(1).join('/') || relativeSlug));
  const headings = headingsFromMarkdown(body);
  const title = metadata.title?.trim() || headings[0] || titleFromSlug(slug.split('/').at(-1) ?? slug);
  const content = body.replace(new RegExp(`^#\\s+${title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*#?\\s*(?:\\n|$)`, 'i'), '').trim();
  const id = `${section.id}/${slug}`;
  return {
    id,
    slug,
    title,
    sectionId: section.id,
    sectionTitle: section.title,
    content,
    headings,
    href: `/docs?article=${encodeURIComponent(id)}`,
    order: Number(metadata.order) || 0,
  };
}

export async function loadDocumentation(): Promise<DocsSnapshot> {
  const files = (await Promise.all(contentRoots.map(async (root) => {
    try {
      return (await markdownFiles(root)).map((filePath) => ({ root, filePath }));
    } catch (error) {
      if (!isRecord(error) || error.code !== 'ENOENT') throw error;
      return [];
    }
  }))).flat();
  const loadedArticles = await Promise.all(files.map(async ({ root, filePath }) => articleFromSource(root, filePath, await readFile(filePath, 'utf8'))));
  const articles = Array.from(new Map(loadedArticles.map((article) => [article.id, article])).values())
    .sort((left, right) => left.order - right.order || left.title.localeCompare(right.title, 'ru'));
  const sections = DOC_SECTION_DEFINITIONS.map((definition) => ({
    ...definition,
    articles: articles.filter((article) => article.sectionId === definition.id),
  }));
  return { sections, articles };
}
