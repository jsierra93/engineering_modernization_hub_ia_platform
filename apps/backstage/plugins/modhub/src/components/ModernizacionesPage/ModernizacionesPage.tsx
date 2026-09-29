import { useEffect, useState } from 'react';
import useAsync from 'react-use/lib/useAsync';
import {
  Page,
  Header,
  Content,
  Table,
  TableColumn,
  Progress,
  ResponseErrorPanel,
  ContentHeader,
  SupportButton,
} from '@backstage/core-components';
import { useApi } from '@backstage/core-plugin-api';
import { useSignal } from '@backstage/plugin-signals-react';
import { Button } from '@material-ui/core';
import { modhubApiRef } from '../../apis';
import { Run } from '../../api/types';
import { CreateRunDialog } from '../CreateRunDialog';
import { ApprovalDialog } from '../ApprovalDialog';
import { ReportDialog } from '../ReportDialog';

const AWAITING_APPROVAL = 'AWAITING_APPROVAL';
const TERMINAL_STATES = [
  'LISTO_PARA_REVISION',
  'COMPLETADO_PARCIALMENTE',
  'FALLIDO_CONTROLADO',
  'BLOQUEADO',
  'PRESUPUESTO_AGOTADO',
  'CANCELADO',
];

const buildColumns = (
  onReview: (run: Run) => void,
  onReport: (runId: string) => void,
): TableColumn<Run>[] => [
  { title: 'Objetivo', field: 'objetivo' },
  { title: 'Repo', field: 'repo' },
  { title: 'Estado', field: 'status' },
  { title: 'Estrategia', field: 'strategy_id' },
  {
    title: 'Costo',
    field: 'spent_usd',
    render: (row: Run) => `$${row.spent_usd.toFixed(2)} / $${row.max_usd.toFixed(2)}`,
  },
  { title: 'Creado', field: 'created_at' },
  {
    title: 'Plan',
    field: 'plan_hash',
    sorting: false,
    render: (row: Run) =>
      row.plan ? (
        <Button size="small" color="primary" onClick={() => onReview(row)}>
          {row.status === AWAITING_APPROVAL ? 'Revisar y aprobar' : 'Ver plan'}
        </Button>
      ) : null,
  },
  {
    title: 'Informe',
    field: 'run_id',
    sorting: false,
    render: (row: Run) =>
      TERMINAL_STATES.includes(row.status) ? (
        <Button size="small" color="primary" onClick={() => onReport(row.run_id)}>
          Ver informe
        </Button>
      ) : null,
  },
];

export const ModernizacionesPage = () => {
  const modhubApi = useApi(modhubApiRef);
  const [createOpen, setCreateOpen] = useState(false);
  const [reviewing, setReviewing] = useState<Run | null>(null);
  const [reportRunId, setReportRunId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const { lastSignal } = useSignal<{ event_type: string }>('modhub:runs');

  useEffect(() => {
    if (lastSignal) {
      setRefreshKey(key => key + 1);
    }
  }, [lastSignal]);

  const { value: runs, loading, error } = useAsync(
    async () => modhubApi.listRuns({ mine: true }),
    [modhubApi, refreshKey],
  );

  return (
    <Page themeId="tool">
      <Header title="Modernizaciones" subtitle="Engineering Modernization Hub" />
      <Content>
        <ContentHeader title="Runs">
          <Button
            variant="contained"
            color="primary"
            onClick={() => setCreateOpen(true)}
          >
            Nueva solicitud
          </Button>
          <SupportButton>
            Crea y sigue solicitudes de modernización sobre repos registrados.
          </SupportButton>
        </ContentHeader>
        {loading && <Progress />}
        {error && <ResponseErrorPanel error={error} />}
        {!loading && !error && (
          <Table
            title="Solicitudes"
            options={{ search: true, paging: true, pageSize: 10 }}
            columns={buildColumns(setReviewing, setReportRunId)}
            data={runs ?? []}
          />
        )}
        <ReportDialog runId={reportRunId} onClose={() => setReportRunId(null)} />
        <ApprovalDialog
          run={reviewing}
          onClose={() => setReviewing(null)}
          onDecided={() => {
            setReviewing(null);
            setRefreshKey(key => key + 1);
          }}
        />
        <CreateRunDialog
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            setRefreshKey(key => key + 1);
          }}
        />
      </Content>
    </Page>
  );
};
