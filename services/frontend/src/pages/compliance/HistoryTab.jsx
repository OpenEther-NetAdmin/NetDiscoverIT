import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Th, Td, Badge, Spinner, Button,
  Text, Flex, useToast,
} from '@chakra-ui/react';
import api from '../../services/api';
import {
  STATUS_COLORS,
  FORMAT_LABELS,
  isTerminalStatus,
  formatReportDate,
} from './complianceUtils';

const POLL_INTERVAL_MS = 3000;

const HistoryTab = ({ triggerReload }) => {
  const toast = useToast();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const pollingRef = useRef(null);

  const loadReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listComplianceReports();
      setReports(Array.isArray(data) ? data : data.items || []);
    } catch (err) {
      setError(err.message);
      toast({
        title: 'Failed to load reports',
        description: err.message,
        status: 'error',
        duration: 4000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadReports();
  }, [loadReports, triggerReload]);

  const hasActiveReports = reports.some((r) => !isTerminalStatus(r.status));

  useEffect(() => {
    if (hasActiveReports && !pollingRef.current) {
      pollingRef.current = setInterval(() => {
        loadReports();
      }, POLL_INTERVAL_MS);
    } else if (!hasActiveReports && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [hasActiveReports, loadReports]);

  const handleDownload = async (reportId) => {
    try {
      const fresh = await api.getComplianceReport(reportId);
      if (fresh.download_url) {
        window.open(fresh.download_url, '_blank', 'noopener,noreferrer');
      } else {
        toast({
          title: 'Download not available',
          description: 'The report is not ready for download yet.',
          status: 'warning',
          duration: 3000,
          isClosable: true,
        });
      }
    } catch (err) {
      toast({
        title: 'Download failed',
        description: err.message,
        status: 'error',
        duration: 4000,
        isClosable: true,
      });
    }
  };

  const handleRetry = async (report) => {
    try {
      await api.createComplianceReport({
        framework: report.framework,
        format: report.format,
        period_start: report.period_start || '',
        period_end: report.period_end || '',
      });
      toast({
        title: 'Report queued for retry',
        status: 'info',
        duration: 3000,
        isClosable: true,
      });
      loadReports();
    } catch (err) {
      toast({
        title: 'Retry failed',
        description: err.message,
        status: 'error',
        duration: 4000,
        isClosable: true,
      });
    }
  };

  const formatFramework = (framework) => {
    if (!framework) return '—';
    return framework.toUpperCase().replace(/_/g, ' ');
  };

  if (loading) {
    return (
      <Flex justify="center" py={8}>
        <Spinner />
      </Flex>
    );
  }

  if (error) {
    return (
      <Box py={8} textAlign="center" color="red.500">
        <Text mb={2}>Failed to load reports</Text>
        <Button size="sm" onClick={loadReports}>
          Retry
        </Button>
      </Box>
    );
  }

  if (!reports.length) {
    return (
      <Box py={8} textAlign="center" color="gray.500">
        No reports yet. Use the Generate tab to create your first report.
      </Box>
    );
  }

  return (
    <Box overflowX="auto">
      <Table size="sm" variant="simple">
        <Thead>
          <Tr>
            <Th>Framework</Th>
            <Th>Format</Th>
            <Th>Status</Th>
            <Th>Started</Th>
            <Th>Action</Th>
          </Tr>
        </Thead>
        <Tbody>
          {reports.map((report) => (
            <Tr key={report.id}>
              <Td fontWeight="medium">{formatFramework(report.framework)}</Td>
              <Td>{FORMAT_LABELS[report.format] || report.format || '—'}</Td>
              <Td>
                <Flex align="center" gap={2}>
                  {!isTerminalStatus(report.status) && <Spinner size="xs" />}
                  <Badge colorScheme={STATUS_COLORS[report.status] || 'gray'}>
                    {report.status || 'pending'}
                  </Badge>
                </Flex>
              </Td>
              <Td fontSize="xs" color="gray.500">
                {formatReportDate(report.created_at) || '—'}
              </Td>
              <Td>
                {report.status === 'completed' && (
                  <Button
                    size="xs"
                    colorScheme="teal"
                    onClick={() => handleDownload(report.id)}
                  >
                    Download
                  </Button>
                )}
                {report.status === 'failed' && (
                  <Button
                    size="xs"
                    colorScheme="orange"
                    variant="outline"
                    onClick={() => handleRetry(report)}
                  >
                    Retry
                  </Button>
                )}
                {!isTerminalStatus(report.status) && (
                  <Text fontSize="xs" color="gray.400">
                    Pending…
                  </Text>
                )}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
};

export default HistoryTab;
