import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { PendingJobsProvider } from './contexts/PendingJobsContext';
import './index.css';

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <PendingJobsProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </PendingJobsProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);

