import { ChakraProvider } from '@chakra-ui/react';
import theme from './theme';
import { Dashboard } from './Dashboard';

function App() {
  return (
    <ChakraProvider theme={theme}>
      <Dashboard />
    </ChakraProvider>
  );
}

export default App;
