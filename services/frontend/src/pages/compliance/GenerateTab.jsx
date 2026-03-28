import React, { useState, useCallback } from 'react';
import {
  Box, Flex, Wrap, WrapItem, Button, Select, Input, FormControl,
  FormLabel, FormErrorMessage, Text, Progress, Alert, AlertIcon,
  AlertTitle, AlertDescription, useToast,
} from '@chakra-ui/react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { FRAMEWORKS, FORMAT_LABELS, daysAgo, today } from './complianceUtils';
import { useReportPolling } from './useReportPolling';

const GenerateTab = ({ onCreated }) => {
  const toast = useToast();
  const [framework, setFramework] = useState('');
  const [format, setFormat] = useState('pdf');
  const [startDate, setStartDate] = useState(daysAgo(365));
  const [endDate, setEndDate] = useState(today());
  const [dateError, setDateError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generatedReportId, setGeneratedReportId] = useState(null);

  const {
    report,
    isPolling,
    error: pollingError,
    startPolling,
    stopPolling,
  } = useReportPolling();

  const validateDates = useCallback((start, end) => {
    if (end <= start) {
      setDateError('End date must be after start date');
      return false;
    }
    setDateError('');
    return true;
  }, []);

  const handleStartChange = (e) => {
    const newStart = e.target.value;
    setStartDate(newStart);
    validateDates(newStart, endDate);
  };

  const handleEndChange = (e) => {
    const newEnd = e.target.value;
    setEndDate(newEnd);
    validateDates(startDate, newEnd);
  };

  const handleSubmit = async () => {
    if (!framework) {
      toast({
        title: 'Framework required',
        description: 'Please select a compliance framework',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (!validateDates(startDate, endDate)) return;

    setIsSubmitting(true);
    setGeneratedReportId(null);
    stopPolling();

    try {
      const reportData = await api.createComplianceReport({
        framework,
        format,
        period_start: startDate,
        period_end: endDate,
      });
      setGeneratedReportId(reportData.id);
      startPolling(reportData.id);
      toast({
        title: 'Report generation started',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });
      if (onCreated) {
        onCreated(reportData.id);
      }
    } catch (err) {
      toast({
        title: 'Failed to create report',
        description: err.message,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    stopPolling();
    setGeneratedReportId(null);
    setFramework('');
    setFormat('pdf');
    setStartDate(daysAgo(365));
    setEndDate(today());
    setDateError('');
  };

  const progressPercent = report?.progress ?? 0;
  const isCompleted = report?.status === 'completed';
  const isFailed = report?.status === 'failed';

  return (
    <Box>
      {!generatedReportId && (
        <>
          <FormControl mb={4} isRequired>
            <FormLabel>Framework</FormLabel>
            <Wrap spacing={2}>
              {FRAMEWORKS.map(({ id, label, colorScheme }) => (
                <WrapItem key={id}>
                  <Button
                    size="sm"
                    colorScheme={colorScheme}
                    variant={framework === id ? 'solid' : 'outline'}
                    onClick={() => setFramework(id)}
                    aria-pressed={framework === id}
                  >
                    {label}
                  </Button>
                </WrapItem>
              ))}
            </Wrap>
            {!framework && (
              <Text fontSize="xs" color="gray.500" mt={1}>
                Select a framework to continue
              </Text>
            )}
          </FormControl>

          <Flex gap={4} mb={4} flexWrap="wrap">
            <FormControl maxW="200px" isInvalid={!!dateError}>
              <FormLabel>Period Start</FormLabel>
              <Input
                type="date"
                value={startDate}
                onChange={handleStartChange}
                aria-label="Period start date"
              />
            </FormControl>
            <FormControl maxW="200px" isInvalid={!!dateError}>
              <FormLabel>Period End</FormLabel>
              <Input
                type="date"
                value={endDate}
                onChange={handleEndChange}
                aria-label="Period end date"
              />
              {dateError && <FormErrorMessage>{dateError}</FormErrorMessage>}
            </FormControl>
          </Flex>

          <FormControl maxW="180px" mb={6}>
            <FormLabel>Format</FormLabel>
            <Select
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              aria-label="Report format"
            >
              {Object.entries(FORMAT_LABELS).map(([val, label]) => (
                <option key={val} value={val}>
                  {label}
                </option>
              ))}
            </Select>
          </FormControl>

          <Button
            colorScheme="blue"
            isDisabled={!framework || !!dateError || isSubmitting}
            isLoading={isSubmitting}
            loadingText="Generating..."
            onClick={handleSubmit}
          >
            Generate Report
          </Button>
        </>
      )}

      {generatedReportId && isPolling && (
        <Box mt={4}>
          <Text mb={2} fontWeight="medium">
            Generating report...
          </Text>
          <Progress
            hasStripe
            isAnimated
            value={progressPercent}
            colorScheme="blue"
            size="sm"
            borderRadius="md"
          />
          <Text fontSize="sm" color="gray.500" mt={1}>
            {progressPercent}% complete
          </Text>
        </Box>
      )}

      {isCompleted && (
        <Alert status="success" mt={4} borderRadius="md">
          <AlertIcon />
          <Box flex="1">
            <AlertTitle>Report generated successfully!</AlertTitle>
            <AlertDescription>
              <Link to={`/compliance/${generatedReportId}`}>
                <Button size="sm" colorScheme="green" mt={2}>
                  View Report
                </Button>
              </Link>
              <Button size="sm" variant="outline" mt={2} ml={2} onClick={handleReset}>
                Generate Another
              </Button>
            </AlertDescription>
          </Box>
        </Alert>
      )}

      {(isFailed || pollingError) && (
        <Alert status="error" mt={4} borderRadius="md">
          <AlertIcon />
          <Box flex="1">
            <AlertTitle>Report generation failed</AlertTitle>
            <AlertDescription>
              {report?.error_message || pollingError || 'An unexpected error occurred'}
              <Button size="sm" variant="outline" mt={2} ml={2} onClick={handleReset}>
                Try Again
              </Button>
            </AlertDescription>
          </Box>
        </Alert>
      )}
    </Box>
  );
};

export default GenerateTab;
