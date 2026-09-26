'use client';

import { Button } from './rtk/button';

export function BackgroundRefreshNotice({ onRetry }: { onRetry: () => void }) {
  return <span role="status" style={{ alignItems: 'center', display: 'inline-flex', flexWrap: 'wrap', fontSize: 12, gap: 8 }}>Не удалось обновить данные. Показана последняя загруженная версия.<Button variant="ghost" size="s" type="button" onClick={onRetry}>Повторить</Button></span>;
}
