import { PageBlueprint, createFrontendPlugin } from '@backstage/frontend-plugin-api';
import { modhubAuthApi, modhubApi } from './apis';

const modernizacionesPage = PageBlueprint.make({
  params: {
    path: '/modhub',
    title: 'Modernizaciones',
    loader: () =>
      import('./components/ModernizacionesPage').then(m => (
        <m.ModernizacionesPage />
      )),
  },
});

export default createFrontendPlugin({
  pluginId: 'modhub',
  extensions: [modernizacionesPage, modhubAuthApi, modhubApi],
});
