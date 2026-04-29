import { useMemo, useState } from 'react';
import { Download, FileCode2, FileDiff, History, RotateCcw, Upload, WandSparkles } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { getConfigVersions } from '../data/mockMonitoring';
import { cn } from '../utils/cn';

function validateConfig(content: string) {
  const issues: string[] = [];

  if (!content.includes('version: 1')) {
    issues.push('Missing required `version: 1` declaration.');
  }

  if (!content.includes('monitors:')) {
    issues.push('Config must contain a `monitors` collection.');
  }

  if (!content.includes('type: http') && !content.includes('type: browser')) {
    issues.push('At least one monitor type must be declared.');
  }

  return issues;
}

function getDiffLines(current: string, previous: string) {
  const currentLines = current.split('\n');
  const previousLineSet = new Set(previous.split('\n'));

  return currentLines
    .filter((line) => !previousLineSet.has(line))
    .map((line) => (line.trim() ? `+ ${line}` : '+'));
}

export default function ConfigEditor() {
  const versions = getConfigVersions();
  const [selectedVersionId, setSelectedVersionId] = useState(versions[0]?.id ?? '');
  const [content, setContent] = useState(versions[0]?.content ?? '');
  const [format, setFormat] = useState<'yaml' | 'json'>('yaml');

  const selectedVersion = versions.find((version) => version.id === selectedVersionId) ?? versions[0];
  const previousVersion = versions[1];
  const validationIssues = useMemo(() => validateConfig(content), [content]);
  const diffLines = useMemo(
    () => getDiffLines(content, previousVersion?.content ?? ''),
    [content, previousVersion?.content]
  );

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-teal-700">Config editor</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Edit the source of truth</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            This mock screen treats config as the primary control plane. UI changes, diff review, version rollback, and
            upload/download flows are all represented here without backend persistence.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="gap-2">
            <Upload className="h-4 w-4" />
            Upload config
          </Button>
          <Button variant="outline" className="gap-2">
            <Download className="h-4 w-4" />
            Download latest
          </Button>
          <Button className="gap-2 bg-teal-900 hover:bg-teal-800">
            <WandSparkles className="h-4 w-4" />
            Validate draft
          </Button>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_0.9fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-slate-200 bg-slate-50/80">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <FileCode2 className="h-5 w-5 text-teal-700" />
                  Config draft
                </CardTitle>
                <p className="mt-2 text-sm text-slate-600">
                  Active version `v{selectedVersion?.version}` by {selectedVersion?.author}
                </p>
              </div>

              <div className="inline-flex rounded-full border border-slate-200 bg-white p-1">
                {(['yaml', 'json'] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setFormat(item)}
                    className={cn(
                      'rounded-full px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] transition-colors',
                      format === item ? 'bg-teal-900 text-white' : 'text-slate-500 hover:text-slate-900'
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
              onChange={(event) => setContent(event.target.value)}
              className="min-h-[28rem] w-full resize-none border-0 bg-slate-950 px-5 py-5 font-mono text-sm leading-7 text-emerald-100 outline-none"
              spellCheck={false}
            />
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Validation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {validationIssues.length === 0 ? (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                  Config looks consistent with the mock schema. Save can remain a UI-only action for now.
                </div>
              ) : (
                validationIssues.map((issue) => (
                  <div key={issue} className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                    {issue}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FileDiff className="h-4 w-4 text-teal-700" />
                Draft diff vs previous
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-2xl bg-slate-950 p-4 font-mono text-xs leading-6 text-emerald-100">
                {diffLines.length === 0 ? (
                  <span className="text-slate-400">No changes from previous version.</span>
                ) : (
                  diffLines.map((line) => <div key={line}>{line}</div>)
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <History className="h-4 w-4 text-teal-700" />
                Version history
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {versions.map((version) => (
                <button
                  key={version.id}
                  type="button"
                  onClick={() => {
                    setSelectedVersionId(version.id);
                    setContent(version.content);
                  }}
                  className={cn(
                    'w-full rounded-2xl border p-4 text-left transition-colors',
                    selectedVersionId === version.id
                      ? 'border-teal-200 bg-teal-50'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">v{version.version}</p>
                      <p className="mt-1 text-xs text-slate-500">{version.createdAt}</p>
                    </div>
                    <Button variant="ghost" size="sm" className="gap-1 text-teal-800">
                      <RotateCcw className="h-3.5 w-3.5" />
                      Rollback
                    </Button>
                  </div>
                  <p className="mt-3 text-sm text-slate-600">{version.summary}</p>
                </button>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
