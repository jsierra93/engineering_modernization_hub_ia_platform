import { useState } from 'react';
import {
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  TextField,
  Typography,
} from '@material-ui/core';
import { useApi } from '@backstage/core-plugin-api';
import { modhubApiRef } from '../../apis';
import { Run } from '../../api/types';

type Props = {
  run: Run | null;
  onClose: () => void;
  onDecided: () => void;
};

export const ApprovalDialog = ({ run, onClose, onDecided }: Props) => {
  const modhubApi = useApi(modhubApiRef);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!run) {
    return null;
  }

  const plan = run.plan ?? null;
  const decidable = run.status === 'AWAITING_APPROVAL';

  const decide = async (decision: 'approve' | 'reject') => {
    if (!run.plan_hash) {
      setError('This run has no plan_hash yet — it is not awaiting approval.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await modhubApi.approve(run.run_id, {
        decision,
        plan_hash: run.plan_hash,
        ...(reason ? { reason } : {}),
      });
      onDecided();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {decidable ? 'Revisar plan de modernización' : `Plan del run (${run.status})`}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="textSecondary">
          {run.repo} @ {run.commit.slice(0, 12)}
        </Typography>
        <Typography variant="body1" style={{ marginTop: 8 }}>
          {run.objetivo}
        </Typography>

        <Divider style={{ margin: '16px 0' }} />

        {!plan && (
          <Typography variant="body2" color="error">
            Este run no tiene el plan almacenado. Fue creado antes de que se
            persistiera el plan, así que solo puedes aprobar contra el hash.
          </Typography>
        )}

        {plan && (
          <>
            <Chip
              size="small"
              label={plan.viable ? 'Viable' : 'No viable'}
              color={plan.viable ? 'primary' : 'secondary'}
            />
            <Typography variant="body2" style={{ marginTop: 8 }}>
              {plan.viability_reason}
            </Typography>

            <Typography variant="subtitle2" style={{ marginTop: 16 }}>
              Resumen
            </Typography>
            <Typography variant="body2">{plan.summary}</Typography>

            <Typography variant="subtitle2" style={{ marginTop: 16 }}>
              Archivos que se modificarán ({plan.planned_changes?.length ?? 0})
            </Typography>
            <ul style={{ marginTop: 4 }}>
              {(plan.planned_changes ?? []).map(change => (
                <li key={change.path}>
                  <code>{change.path}</code> — {change.reason}
                </li>
              ))}
            </ul>

            {(plan.risks ?? []).length > 0 && (
              <>
                <Typography variant="subtitle2" style={{ marginTop: 8 }}>
                  Riesgos
                </Typography>
                <ul style={{ marginTop: 4 }}>
                  {(plan.risks ?? []).map(risk => (
                    <li key={risk}>{risk}</li>
                  ))}
                </ul>
              </>
            )}

            <Typography variant="subtitle2" style={{ marginTop: 8 }}>
              Fuentes consultadas ({plan.sources?.length ?? 0})
            </Typography>
            <ul style={{ marginTop: 4 }}>
              {(plan.sources ?? []).map(source => (
                <li key={source}>
                  <a href={source} target="_blank" rel="noreferrer">
                    {source}
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}

        <Divider style={{ margin: '16px 0' }} />

        <Typography variant="caption" color="textSecondary">
          plan_hash: <code>{run.plan_hash}</code>
        </Typography>
        <Typography variant="caption" component="p" color="textSecondary">
          La aprobación se valida contra este hash. Si el plan cambiara, la
          aprobación quedaría obsoleta y sería rechazada.
        </Typography>

        {decidable && (
        <TextField
          label="Motivo (obligatorio al rechazar)"
          fullWidth
          multiline
          minRows={2}
          value={reason}
          onChange={event => setReason(event.target.value)}
          style={{ marginTop: 16 }}
        />
        )}

        {error && (
          <Typography variant="body2" color="error" style={{ marginTop: 8 }}>
            {error}
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          {decidable ? 'Cancelar' : 'Cerrar'}
        </Button>
        {decidable && (
          <>
            <Button
              onClick={() => decide('reject')}
              disabled={submitting || !reason}
              color="secondary"
            >
              Rechazar
            </Button>
            <Button
              onClick={() => decide('approve')}
              disabled={submitting}
              color="primary"
              variant="contained"
            >
              Aprobar
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};
