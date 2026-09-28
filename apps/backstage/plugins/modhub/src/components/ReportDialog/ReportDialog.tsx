import { useState } from 'react';
import useAsync from 'react-use/lib/useAsync';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Typography,
} from '@material-ui/core';
import { Progress, ResponseErrorPanel } from '@backstage/core-components';
import { alertApiRef, useApi } from '@backstage/core-plugin-api';
import { modhubApiRef } from '../../apis';

// The five final states come from the brief verbatim, so none of them can
// be split. But one state answers "what happened" and not "why": the same
// FALLIDO_CONTROLADO covers an exhausted fix loop and a weakened test
// suite. reason_code carries the branch core_ops actually took.
const REASON_LABEL: Record<string, string> = {
  INFEASIBLE: 'El agente concluyó que la modernización no es viable',
  BASELINE_FAILING: 'El repositorio ya fallaba antes de tocarlo',
  BUDGET_USD_EXHAUSTED: 'Se agotó el presupuesto en dólares',
  TIME_EXHAUSTED: 'Se agotó el tiempo máximo',
  ITERATIONS_EXHAUSTED: 'Se agotaron las iteraciones',
  FIX_ITERATIONS_EXHAUSTED: 'Se agotaron las correcciones sin pasar las pruebas',
  UNRECOVERABLE_ERROR: 'Error no recuperable del modelo o de una herramienta',
  APPROVAL_TIMED_OUT: 'Nadie aprobó el plan dentro del plazo',
  SUITE_VIOLATION: 'La suite de pruebas se debilitó',
  SCOPE_ESCAPE: 'Se modificaron archivos fuera del alcance aprobado',
  NO_CHANGES_PRODUCED: 'El agente no produjo ningún cambio',
  BLOCKING_CHECK_FAILED: 'Falló una verificación bloqueante',
  NON_BLOCKING_CHECK_FAILED: 'Falló una verificación no bloqueante (lint)',
  ALL_CHECKS_PASSED: 'Todas las verificaciones pasaron',
};

type Props = {
  runId: string | null;
  onClose: () => void;
};

export const ReportDialog = ({ runId, onClose }: Props) => {
  const modhubApi = useApi(modhubApiRef);
  const alertApi = useApi(alertApiRef);
  const [publishing, setPublishing] = useState(false);
  const [createdPrUrl, setCreatedPrUrl] = useState<string | null>(null);
  const { value: report, loading, error } = useAsync(
    async () => (runId ? modhubApi.getReport(runId) : undefined),
    [modhubApi, runId],
  );

  // The report is the durable record; local state only covers the moment
  // between creating a PR and the next fetch.
  const prUrl = createdPrUrl ?? report?.pull_request_url ?? null;

  if (!runId) {
    return null;
  }

  const publish = async () => {
    if (!runId) {
      return;
    }
    setPublishing(true);
    try {
      const created = await modhubApi.openPullRequest(runId);
      setCreatedPrUrl(created.pull_request_url);
      alertApi.post({ message: `PR creado: ${created.pull_request_url}`, severity: 'success' });
    } catch (caught) {
      alertApi.post({
        message: caught instanceof Error ? caught.message : String(caught),
        severity: 'error',
      });
    } finally {
      setPublishing(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Informe de modernización</DialogTitle>
      <DialogContent>
        {loading && <Progress />}
        {error && <ResponseErrorPanel error={error} />}

        {report && (
          <>
            <Typography variant="body2" color="textSecondary">
              {report.repo} @ {report.commit.slice(0, 12)}
            </Typography>
            <Typography variant="h6" style={{ marginTop: 8 }}>
              {report.verdict.status}
            </Typography>
            {report.reason_code && (
              <Typography variant="body2" color="textSecondary">
                {REASON_LABEL[report.reason_code] ?? report.reason_code}
              </Typography>
            )}
            <Typography variant="body2">
              ${report.verdict.spent_usd.toFixed(4)} de ${report.verdict.max_usd.toFixed(2)} ·{' '}
              {report.verdict.iterations_used}/{report.verdict.max_iterations} iteraciones ·{' '}
              estrategia {report.strategy.id}
            </Typography>

            <Divider style={{ margin: '16px 0' }} />

            {report.narrative.summary && (
              <>
                <Typography variant="subtitle2">Qué se hizo</Typography>
                <Typography variant="body2">{report.narrative.summary}</Typography>
              </>
            )}

            {/* A run that concluded infeasibility has no summary -- nothing
                was going to change. Its reasoning is the deliverable, so it
                gets the heading instead of leaving an empty block. */}
            {report.narrative.viability_reason && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: report.narrative.summary ? 16 : 0 }}>
                  {report.verdict.status === 'BLOQUEADO' ? 'Por qué no se puede' : 'Viabilidad'}
                </Typography>
                <Typography variant="body2">{report.narrative.viability_reason}</Typography>
              </>
            )}

            {(report.narrative.risks ?? []).length > 0 && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: 16 }}>
                  Riesgos identificados
                </Typography>
                <ul style={{ marginTop: 4 }}>
                  {(report.narrative.risks ?? []).map(risk => (
                    <li key={risk}>
                      <Typography variant="body2">{risk}</Typography>
                    </li>
                  ))}
                </ul>
              </>
            )}

            {(report.narrative.sources ?? []).length > 0 && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: 16 }}>
                  Fuentes consultadas
                </Typography>
                <ul style={{ marginTop: 4 }}>
                  {(report.narrative.sources ?? []).map(source => (
                    <li key={source}>
                      <a href={source} target="_blank" rel="noreferrer">
                        {source}
                      </a>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <Typography variant="subtitle2" style={{ marginTop: 16 }}>
              Archivos modificados ({report.changed_paths.length})
            </Typography>
            <ul style={{ marginTop: 4 }}>
              {report.changed_paths.map(path => (
                <li key={path}>
                  <code>{path}</code>
                </li>
              ))}
            </ul>

            {(report.security_events ?? []).length > 0 && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: 16 }}>
                  Eventos de seguridad ({(report.security_events ?? []).length})
                </Typography>
                <ul style={{ marginTop: 4 }}>
                  {(report.security_events ?? []).map((event, index) => (
                    <li key={`${event.type}-${index}`}>
                      <Typography variant="body2">
                        <code>{event.type}</code>
                        {event.message ? ` — ${event.message}` : ''}
                        {typeof event.data?.attempted_path === 'string'
                          ? ` (${event.data.attempted_path})`
                          : ''}
                      </Typography>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <Typography variant="subtitle2" style={{ marginTop: 16 }}>
              Modelos usados
            </Typography>
            <Typography variant="body2">
              {Object.entries(report.models_used)
                .map(([phase, model]) => `${phase}: ${model}`)
                .join(' · ') || '—'}
            </Typography>

            {report.diff && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: 16 }}>
                  Diff
                </Typography>
                <pre
                  style={{
                    maxHeight: 320,
                    overflow: 'auto',
                    fontSize: 12,
                    background: 'rgba(0,0,0,0.25)',
                    padding: 12,
                  }}
                >
                  {report.diff}
                </pre>
              </>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        {prUrl ? (
          <Button href={prUrl} target="_blank" color="primary" variant="contained">
            Ver PR
          </Button>
        ) : (
          <Button
            onClick={publish}
            color="primary"
            variant="contained"
            disabled={publishing || !report?.changed_paths.length}
          >
            {publishing ? 'Creando PR...' : 'Crear PR'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};
