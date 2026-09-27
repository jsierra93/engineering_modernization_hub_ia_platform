import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { HomePageWidgetBlueprint } from '@backstage/plugin-home-react/alpha';
import { MarkdownContent } from '@backstage/core-components';

const content = `
## Engineering Modernization Hub 🚀

Bienvenido al hub de modernización. Accede a **Modernizaciones** en el sidebar para crear y seguir tus solicitudes.

### Quick Links
- **[Modernizaciones](/modhub)** - Crea y gestiona tus modernizaciones
`;

const gettingStartedWidget = HomePageWidgetBlueprint.make({
  name: 'getting-started',
  params: {
    name: 'GettingStarted',
    title: 'Inicio',
    description: 'Portal de modernización de código',
    components: async () => ({
      Content: () => <MarkdownContent content={content} />,
    }),
  },
});

export const homeModule = createFrontendModule({
  pluginId: 'home',
  extensions: [gettingStartedWidget],
});
