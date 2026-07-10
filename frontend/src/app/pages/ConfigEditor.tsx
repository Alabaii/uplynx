import { useEffect, useMemo, useState } from 'react';
import { Download, FileCode2, FileDiff, History, RotateCcw, Upload, WandSparkles } from 'lucide-react';
import YAML from 'yaml';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { getConfig, listConfigVersions, rollbackConfig, uploadConfig, type ConfigVersion } from '../api';
import { useTexts } from '../i18n';
import { cn } from '../utils/cn';

type ValidationTexts = {
  parseError: (message: string) => string;
  notMapping: string;
  badVersion: string;
  noMonitorsList: string;
  monitorNotMapping: (index: number) => string;
  monitorMissingId: (label: string) => string;
  monitorBadType: (label: string) => string;
  httpMonitorNeedsUrl: (label: string) => string;
  browserMonitorNeedsSteps: (label: string) => string;
};

function validateDraft(content: string, format: 'yaml' | 'json', t: ValidationTexts): string[] {
  let parsed: unknown;

  try {
    parsed = format === 'json' ? JSON.parse(content) : YAML.parse(content);
  } catch (error) {
    return [t.parseError(error instanceof Error ? error.message : String(error))];
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return [t.notMapping];
  }

  const doc = parsed as Record<string, unknown>;
  const issues: string[] = [];

  if (doc.version !== 1) {
    issues.push(t.badVersion);
  }

  if (!Array.isArray(doc.monitors)) {
    issues.push(t.noMonitorsList);
    return issues;
  }

  doc.monitors.forEach((monitor, index) => {
    if (!monitor || typeof monitor !== 'object' || Array.isArray(monitor)) {
      issues.push(t.monitorNotMapping(index + 1));
      return;
    }

    const item = monitor as Record<string, unknown>;
    const label = typeof item.id === 'string' && item.id ? `\`${item.id}\`` : `#${index + 1}`;

    if (typeof item.id !== 'string' || !item.id) {
      issues.push(t.monitorMissingId(label));
    }

    if (item.type !== 'http' && item.type !== 'browser') {
      issues.push(t.monitorBadType(label));
    }

    if (item.type === 'http' && (typeof item.url !== 'string' || !item.url)) {
      issues.push(t.httpMonitorNeedsUrl(label));
    }

    if (item.type === 'browser' && (!Array.isArray(item.steps) || item.steps.length === 0)) {
      issues.push(t.browserMonitorNeedsSteps(label));
    }
  });

  return issues;
}

function getDiffLines(current: string, previous: string) {
  const currentLines = current.split('\n');
  const previousLines = previous.split('\n');
  const currentLineSet = new Set(currentLines);
  const previousLineSet = new Set(previousLines);

  const added = currentLines
    .filter((line) => !previousLineSet.has(line))
    .map((line) => (line.trim() ? `+ ${line}` : '+'));
  const removed = previousLines
    .filter((line) => !currentLineSet.has(line))
    .map((line) => (line.trim() ? `- ${line}` : '-'));

  return [...removed, ...added];
}

export default function ConfigEditor() {
  const t = useTexts({
    ru: {
      parseError: (message: string) => `Ошибка разбора: ${message}`,
      notMapping: 'Конфиг должен быть маппингом с ключами `version` и `monitors`.',
      badVersion: 'Отсутствует или неверный `version` (ожидается `version: 1`).',
      noMonitorsList: 'Конфиг должен содержать список `monitors`.',
      monitorNotMapping: (index: number) => `Монитор #${index} должен быть маппингом.`,
      monitorMissingId: (label: string) => `У монитора ${label} отсутствует \`id\`.`,
      monitorBadType: (label: string) => `Монитор ${label} должен объявлять \`type: http\` или \`type: browser\`.`,
      httpMonitorNeedsUrl: (label: string) => `HTTP-монитору ${label} требуется \`url\`.`,
      browserMonitorNeedsSteps: (label: string) => `Browser-монитору ${label} требуется непустой список \`steps\`.`,
      loadError: 'Не удалось загрузить конфиг',
      uploaded: (version: number) => `Загружен конфиг v${version}`,
      uploadError: 'Не удалось загрузить конфиг на сервер',
      rolledBack: (from: number, savedAs: number) => `Выполнен откат к v${from} (сохранено как v${savedAs})`,
      rollbackError: 'Не удалось откатить конфиг',
      kicker: 'Редактор конфига',
      title: 'Редактирование источника правды',
      description:
        'Этот экран рассматривает конфиг как основную панель управления. Загрузка и скачивание подключены к хранилищу на бэкенде.',
      uploadConfig: 'Загрузить конфиг',
      downloadLatest: 'Скачать актуальный',
      validateDraft: 'Проверить черновик',
      configDraft: 'Черновик конфига',
      activeVersion: (version: number | string) =>
        `Активная версия \`v${version}\` из хранилища конфигов на бэкенде`,
      validation: 'Валидация',
      runValidationHint: 'Нажмите `Проверить черновик`, чтобы проверить конфиг перед загрузкой.',
      validationOk: 'Конфиг успешно разобран и соответствует ожидаемой структуре.',
      diffTitle: 'Отличия черновика от сохранённой версии',
      noChanges: 'Нет изменений относительно сохранённой версии.',
      versionHistory: 'История версий',
      rollback: 'Откат',
      formatLabel: 'Формат:',
    },
    en: {
      parseError: (message: string) => `Parse error: ${message}`,
      notMapping: 'Config must be a mapping with `version` and `monitors` keys.',
      badVersion: 'Missing or invalid `version` (expected `version: 1`).',
      noMonitorsList: 'Config must contain a `monitors` list.',
      monitorNotMapping: (index: number) => `Monitor #${index} must be a mapping.`,
      monitorMissingId: (label: string) => `Monitor ${label} is missing an \`id\`.`,
      monitorBadType: (label: string) => `Monitor ${label} must declare \`type: http\` or \`type: browser\`.`,
      httpMonitorNeedsUrl: (label: string) => `HTTP monitor ${label} requires a \`url\`.`,
      browserMonitorNeedsSteps: (label: string) => `Browser monitor ${label} requires a non-empty \`steps\` list.`,
      loadError: 'Unable to load config',
      uploaded: (version: number) => `Uploaded config v${version}`,
      uploadError: 'Unable to upload config',
      rolledBack: (from: number, savedAs: number) => `Rolled back to v${from} (saved as v${savedAs})`,
      rollbackError: 'Unable to roll back config',
      kicker: 'Config editor',
      title: 'Edit the source of truth',
      description:
        'This screen treats config as the primary control plane. Upload/download flows are connected to backend persistence.',
      uploadConfig: 'Upload config',
      downloadLatest: 'Download latest',
      validateDraft: 'Validate draft',
      configDraft: 'Config draft',
      activeVersion: (version: number | string) =>
        `Active version \`v${version}\` from backend config storage`,
      validation: 'Validation',
      runValidationHint: 'Run `Validate draft` to check the config before uploading.',
      validationOk: 'Config parses correctly and matches the expected structure.',
      diffTitle: 'Draft diff vs saved version',
      noChanges: 'No changes from the saved version.',
      versionHistory: 'Version history',
      rollback: 'Rollback',
      formatLabel: 'Format:',
    },
  });

  const [versions, setVersions] = useState<ConfigVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [content, setContent] = useState('version: 1\nmonitors: []\n');
  const [savedContent, setSavedContent] = useState('version: 1\nmonitors: []\n');
  const [format, setFormat] = useState<'yaml' | 'json'>('yaml');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [validationIssues, setValidationIssues] = useState<string[] | null>(null);

  useEffect(() => {
    let ignore = false;

    Promise.all([getConfig(), listConfigVersions()])
      .then(([config, versionList]) => {
        if (!ignore) {
          setContent(config.content);
          setSavedContent(config.content);
          setFormat(config.format === 'json' ? 'json' : 'yaml');
          setVersions(versionList);
          setSelectedVersionId(versionList[0]?.id ?? null);
          setError('');
        }
      })
      .catch((error) => {
        if (!ignore) {
          setError(error instanceof Error ? error.message : t.loadError);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const selectedVersion = versions.find((version) => version.id === selectedVersionId) ?? versions[0];
  const diffLines = useMemo(() => getDiffLines(content, savedContent), [content, savedContent]);

  const reloadConfig = async () => {
    const [config, versionList] = await Promise.all([getConfig(), listConfigVersions()]);

    setContent(config.content);
    setSavedContent(config.content);
    setFormat(config.format === 'json' ? 'json' : 'yaml');
    setVersions(versionList);
    setSelectedVersionId(versionList[0]?.id ?? null);
    setValidationIssues(null);
  };

  const handleUpload = async () => {
    setError('');
    setMessage('');

    try {
      const version = await uploadConfig(content, format);
      const versionList = await listConfigVersions();

      setSavedContent(content);
      setVersions(versionList);
      setSelectedVersionId(version.id);
      setMessage(t.uploaded(version.version));
    } catch (error) {
      setError(error instanceof Error ? error.message : t.uploadError);
    }
  };

  const handleRollback = async (version: ConfigVersion) => {
    setError('');
    setMessage('');

    try {
      const restored = await rollbackConfig(version.version);

      await reloadConfig();
      setMessage(t.rolledBack(version.version, restored.version));
    } catch (error) {
      setError(error instanceof Error ? error.message : t.rollbackError);
    }
  };

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 rounded-lg bg-card p-6 shadow-card lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary">{t.kicker}</p>
          <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">{t.title}</h1>
          <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">
            {t.description}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={handleUpload}>
            <Upload className="h-4 w-4" />
            {t.uploadConfig}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'application/x-yaml' });
              const url = URL.createObjectURL(blob);
              const link = document.createElement('a');
              link.href = url;
              link.download = `monitor-config.${format}`;
              link.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download className="h-4 w-4" />
            {t.downloadLatest}
          </Button>
          <Button onClick={() => setValidationIssues(validateDraft(content, format, t))}>
            <WandSparkles className="h-4 w-4" />
            {t.validateDraft}
          </Button>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_0.9fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <FileCode2 className="h-5 w-5 text-primary" />
                  {t.configDraft}
                </CardTitle>
                <p className="mt-2 text-sm text-muted-foreground">
                  {t.activeVersion(selectedVersion?.version ?? 'draft')}
                </p>
              </div>

              <div className="inline-flex rounded-xl bg-secondary p-1">
                {(['yaml', 'json'] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => {
                      setFormat(item);
                      setValidationIssues(null);
                    }}
                    className={cn(
                      'rounded-md px-4 py-1.5 text-sm font-medium uppercase transition-colors',
                      format === item ? 'bg-card text-primary' : 'text-muted-foreground hover:text-primary'
                    )}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            <textarea
              value={content}
              onChange={(event) => {
                setContent(event.target.value);
                setValidationIssues(null);
              }}
              className="min-h-[28rem] w-full resize-none border-0 bg-[#2C2D2E] px-5 py-5 font-mono text-sm leading-7 text-[#E6F7F3] outline-none"
              spellCheck={false}
            />
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>{t.validation}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {message && (
                <div className="rounded-lg bg-accent p-4 text-sm text-accent-foreground">
                  {message}
                </div>
              )}
              {error && (
                <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">
                  {error}
                </div>
              )}
              {validationIssues === null ? (
                <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">
                  {t.runValidationHint}
                </div>
              ) : validationIssues.length === 0 ? (
                <div className="rounded-lg bg-accent p-4 text-sm text-accent-foreground">
                  {t.validationOk}
                </div>
              ) : (
                validationIssues.map((issue) => (
                  <div key={issue} className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">
                    {issue}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileDiff className="h-4 w-4 text-primary" />
                {t.diffTitle}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg bg-secondary p-4 font-mono text-xs leading-6 text-foreground">
                {diffLines.length === 0 ? (
                  <span className="text-placeholder">{t.noChanges}</span>
                ) : (
                  diffLines.map((line, index) => (
                    <div
                      key={`${index}-${line}`}
                      className={cn(
                        'rounded-sm px-1',
                        line.startsWith('-') ? 'bg-destructive/10 text-destructive' : 'bg-accent text-status-up'
                      )}
                    >
                      {line}
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <History className="h-4 w-4 text-primary" />
                {t.versionHistory}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {versions.map((version) => (
                <div
                  key={version.id}
                  className={cn(
                    'w-full rounded-lg border p-4 text-left transition-colors',
                    selectedVersionId === version.id
                      ? 'border-transparent bg-accent'
                      : 'border-border bg-card hover:border-input-border-hover'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-foreground">v{version.version}</p>
                      <p className="mt-1 text-xs text-placeholder">{new Date(version.created_at).toLocaleString()}</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="gap-1"
                      onClick={() => handleRollback(version)}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      {t.rollback}
                    </Button>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">{t.formatLabel} {version.format}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
