import { useEffect, useMemo, useState } from 'react';
import { Download, FileCode2, FileDiff, History, RotateCcw, Upload, WandSparkles } from 'lucide-react';
import YAML from 'yaml';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { getConfig, listConfigVersions, rollbackConfig, uploadConfig, type ConfigVersion } from '../api';
import { cn } from '../utils/cn';

function validateDraft(content: string, format: 'yaml' | 'json'): string[] {
  let parsed: unknown;

  try {
    parsed = format === 'json' ? JSON.parse(content) : YAML.parse(content);
  } catch (error) {
    return [`Parse error: ${error instanceof Error ? error.message : String(error)}`];
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return ['Config must be a mapping with `version` and `monitors` keys.'];
  }

  const doc = parsed as Record<string, unknown>;
  const issues: string[] = [];

  if (doc.version !== 1) {
    issues.push('Missing or invalid `version` (expected `version: 1`).');
  }

  if (!Array.isArray(doc.monitors)) {
    issues.push('Config must contain a `monitors` list.');
    return issues;
  }

  doc.monitors.forEach((monitor, index) => {
    if (!monitor || typeof monitor !== 'object' || Array.isArray(monitor)) {
      issues.push(`Monitor #${index + 1} must be a mapping.`);
      return;
    }

    const item = monitor as Record<string, unknown>;
    const label = typeof item.id === 'string' && item.id ? `\`${item.id}\`` : `#${index + 1}`;

    if (typeof item.id !== 'string' || !item.id) {
      issues.push(`Monitor ${label} is missing an \`id\`.`);
    }

    if (item.type !== 'http' && item.type !== 'browser') {
      issues.push(`Monitor ${label} must declare \`type: http\` or \`type: browser\`.`);
    }

    if (item.type === 'http' && (typeof item.url !== 'string' || !item.url)) {
      issues.push(`HTTP monitor ${label} requires a \`url\`.`);
    }

    if (item.type === 'browser' && (!Array.isArray(item.steps) || item.steps.length === 0)) {
      issues.push(`Browser monitor ${label} requires a non-empty \`steps\` list.`);
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
          setError(error instanceof Error ? error.message : 'Unable to load config');
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
      setMessage(`Uploaded config v${version.version}`);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to upload config');
    }
  };

  const handleRollback = async (version: ConfigVersion) => {
    setError('');
    setMessage('');

    try {
      const restored = await rollbackConfig(version.version);

      await reloadConfig();
      setMessage(`Rolled back to v${version.version} (saved as v${restored.version})`);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to roll back config');
    }
  };

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 rounded-lg bg-card p-6 shadow-card lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary">Config editor</p>
          <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">Edit the source of truth</h1>
          <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">
            This screen treats config as the primary control plane. Upload/download flows are connected to backend persistence.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={handleUpload}>
            <Upload className="h-4 w-4" />
            Upload config
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
            Download latest
          </Button>
          <Button onClick={() => setValidationIssues(validateDraft(content, format))}>
            <WandSparkles className="h-4 w-4" />
            Validate draft
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
                  Config draft
                </CardTitle>
                <p className="mt-2 text-sm text-muted-foreground">
                  Active version `v{selectedVersion?.version ?? 'draft'}` from backend config storage
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
              <CardTitle>Validation</CardTitle>
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
                  Run `Validate draft` to check the config before uploading.
                </div>
              ) : validationIssues.length === 0 ? (
                <div className="rounded-lg bg-accent p-4 text-sm text-accent-foreground">
                  Config parses correctly and matches the expected structure.
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
                Draft diff vs saved version
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg bg-secondary p-4 font-mono text-xs leading-6 text-foreground">
                {diffLines.length === 0 ? (
                  <span className="text-placeholder">No changes from the saved version.</span>
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
                Version history
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
                      Rollback
                    </Button>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">Format: {version.format}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
