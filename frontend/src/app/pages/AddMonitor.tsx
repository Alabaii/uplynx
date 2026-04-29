import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { Check, ChevronLeft, FileSearch, Globe, MousePointerClick, Save, Type, WandSparkles } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { cn } from '../utils/cn';
import type { BrowserStepAction, MonitorType } from '../data/mockMonitoring';

type BuilderStep = {
  id: string;
  action: BrowserStepAction;
  label: string;
  selector?: string;
  value?: string;
  url?: string;
  expectedText?: string;
};

const starterSteps: BuilderStep[] = [
  { id: 'draft-1', action: 'goto', label: 'Open page', url: 'https://example.com' },
];

const stepLabels: Record<BrowserStepAction, string> = {
  goto: 'Open page',
  click: 'Click target',
  type: 'Type text',
  assert_text: 'Assert text',
};

const stepIcons: Record<BrowserStepAction, typeof Globe> = {
  goto: Globe,
  click: MousePointerClick,
  type: Type,
  assert_text: FileSearch,
};

export default function AddMonitor() {
  const navigate = useNavigate();
  const [monitorType, setMonitorType] = useState<MonitorType>('http');
  const [isSaving, setIsSaving] = useState(false);
  const [steps, setSteps] = useState<BuilderStep[]>(starterSteps);

  const submitCopy = useMemo(
    () => (monitorType === 'http' ? 'Save HTTP monitor' : 'Save browser monitor'),
    [monitorType]
  );

  const addStep = (action: BrowserStepAction) => {
    setSteps((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        action,
        label: stepLabels[action],
        selector: '',
        value: '',
        url: '',
        expectedText: '',
      },
    ]);
  };

  const updateStep = (id: string, key: keyof BuilderStep, value: string) => {
    setSteps((current) => current.map((step) => (step.id === id ? { ...step, [key]: value } : step)));
  };

  const removeStep = (id: string) => {
    setSteps((current) => current.filter((step) => step.id !== id));
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);

    window.setTimeout(() => {
      setIsSaving(false);
      navigate('/');
    }, 900);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900">
          <ChevronLeft className="h-5 w-5" />
        </Link>
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.22em] text-teal-700">New monitor</p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Build from UI, keep config-ready</h1>
        </div>
      </div>

      <Card>
        <CardHeader className="border-b border-slate-200 bg-slate-50/80">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="text-xl">Monitor builder</CardTitle>
              <p className="mt-2 text-sm text-slate-600">
                Model either a fast HTTP probe or a full browser scenario. Save remains a UI-only action for now.
              </p>
            </div>
            <div className="flex rounded-full border border-slate-200 bg-white p-1">
              <TypeToggle active={monitorType === 'http'} onClick={() => setMonitorType('http')}>
                HTTP
              </TypeToggle>
              <TypeToggle active={monitorType === 'browser'} onClick={() => setMonitorType('browser')}>
                Browser
              </TypeToggle>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <Input label="Monitor name" placeholder="Production API health" required />
              <Input label="Target URL" placeholder="https://api.example.com/health" required />
              <Input label="Interval (seconds)" type="number" defaultValue={monitorType === 'http' ? 60 : 300} required />
              <Input label="Runtime location" placeholder="eu-central-1" defaultValue="eu-central-1" required />
            </div>

            {monitorType === 'http' ? (
              <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1.2fr]">
                <Input label="Expected status" type="number" placeholder="200" defaultValue="200" required />
                <Input label="Timeout (seconds)" type="number" placeholder="30" defaultValue="30" required />
                <Input label="Body contains" placeholder="ok" defaultValue="ok" />
              </div>
            ) : (
              <div className="space-y-5">
                <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-950">Scenario builder</h3>
                      <p className="mt-1 text-sm text-slate-600">
                        Supported mock actions: `goto`, `click`, `type`, `assert_text`.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(['goto', 'click', 'type', 'assert_text'] as const).map((action) => {
                        const Icon = stepIcons[action];

                        return (
                          <Button
                            key={action}
                            type="button"
                            variant="outline"
                            size="sm"
                            className="gap-1.5 bg-white"
                            onClick={() => addStep(action)}
                          >
                            <Icon className="h-3.5 w-3.5" />
                            {stepLabels[action]}
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  {steps.map((step, index) => {
                    const Icon = stepIcons[step.action];

                    return (
                      <div key={step.id} className="rounded-[1.5rem] border border-slate-200 bg-white p-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
                              <Icon className="h-5 w-5" />
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-slate-900">Step {index + 1}</p>
                              <p className="text-sm text-slate-500">{step.action}</p>
                            </div>
                          </div>

                          {steps.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeStep(step.id)}
                              className="text-sm font-medium text-rose-600 hover:text-rose-500"
                            >
                              Remove
                            </button>
                          )}
                        </div>

                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                          <Input
                            label="Step label"
                            value={step.label}
                            onChange={(event) => updateStep(step.id, 'label', event.target.value)}
                            required
                          />
                          {step.action === 'goto' && (
                            <Input
                              label="URL"
                              value={step.url}
                              onChange={(event) => updateStep(step.id, 'url', event.target.value)}
                              required
                            />
                          )}
                          {step.action === 'click' && (
                            <Input
                              label="Selector"
                              value={step.selector}
                              onChange={(event) => updateStep(step.id, 'selector', event.target.value)}
                              required
                            />
                          )}
                          {step.action === 'type' && (
                            <>
                              <Input
                                label="Selector"
                                value={step.selector}
                                onChange={(event) => updateStep(step.id, 'selector', event.target.value)}
                                required
                              />
                              <Input
                                label="Value"
                                value={step.value}
                                onChange={(event) => updateStep(step.id, 'value', event.target.value)}
                                required
                              />
                            </>
                          )}
                          {step.action === 'assert_text' && (
                            <Input
                              label="Expected text"
                              value={step.expectedText}
                              onChange={(event) => updateStep(step.id, 'expectedText', event.target.value)}
                              required
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="rounded-[1.5rem] border border-teal-200 bg-teal-50 px-4 py-4 text-sm text-teal-900">
              <div className="flex items-start gap-3">
                <WandSparkles className="mt-0.5 h-4 w-4 shrink-0" />
                UI save will later serialize this form back into config YAML/JSON and trigger a scheduler hot reload.
              </div>
            </div>

            <div className="flex flex-col gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:justify-end">
              <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
                Cancel
              </Button>
              <Button type="submit" className="gap-2 bg-teal-900 hover:bg-teal-800" isLoading={isSaving}>
                <Save className="h-4 w-4" />
                {submitCopy}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-3">
          <PreviewBullet label="Schema normalization" text="Types already use `http | browser` and browser actions align with PRD." />
          <PreviewBullet label="Config parity" text="Every form field corresponds to a config property that can be exported later." />
          <PreviewBullet label="Scenario UX" text="Steps are reorder-ready and readable enough for a future no-code builder." />
        </CardContent>
      </Card>
    </div>
  );
}

function TypeToggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full px-4 py-2 text-sm font-semibold transition-colors',
        active ? 'bg-teal-900 text-white' : 'text-slate-600 hover:text-slate-900'
      )}
    >
      {children}
    </button>
  );
}

function PreviewBullet({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Check className="h-4 w-4 text-emerald-600" />
        {label}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-600">{text}</p>
    </div>
  );
}
