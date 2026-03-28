import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../services/api';
import { isTerminalStatus } from './complianceUtils';

const POLLING_INTERVAL_MS = 4000;

export function useReportPolling() {
  const [report, setReport] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState(null);

  const intervalRef = useRef(null);
  const reportIdRef = useRef(null);
  const mountedRef = useRef(true);

  const clearPollingInterval = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const fetchReportStatus = useCallback(async (reportId) => {
    try {
      const freshReport = await api.getComplianceReport(reportId);
      if (!mountedRef.current) return;
      setReport(freshReport);
      setError(null);

      if (isTerminalStatus(freshReport.status)) {
        clearPollingInterval();
        setIsPolling(false);
        reportIdRef.current = null;
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err.message || 'Failed to fetch report status');
    }
  }, [clearPollingInterval]);

  const startPolling = useCallback((reportId) => {
    if (!reportId) return;

    clearPollingInterval();
    reportIdRef.current = reportId;
    setError(null);
    setIsPolling(true);

    fetchReportStatus(reportId);

    intervalRef.current = setInterval(() => {
      if (reportIdRef.current) {
        fetchReportStatus(reportIdRef.current);
      }
    }, POLLING_INTERVAL_MS);
  }, [clearPollingInterval, fetchReportStatus]);

  const stopPolling = useCallback(() => {
    clearPollingInterval();
    reportIdRef.current = null;
    setIsPolling(false);
  }, [clearPollingInterval]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearPollingInterval();
    };
  }, [clearPollingInterval]);

  return {
    report,
    isPolling,
    error,
    startPolling,
    stopPolling,
  };
}

export default useReportPolling;
