import React, { useState, useCallback } from 'react';
import {
  Box, Heading, Tabs, TabList, Tab, TabPanels, TabPanel,
} from '@chakra-ui/react';
import GenerateTab from './GenerateTab';
import HistoryTab from './HistoryTab';

const ComplianceViewer = () => {
  const [tabIndex, setTabIndex] = useState(0);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const handleReportCreated = useCallback(() => {
    setHistoryRefreshKey((k) => k + 1);
    setTabIndex(1);
  }, []);

  return (
    <Box p={6}>
      <Heading mb={6} size="lg">
        Compliance Reports
      </Heading>
      <Tabs index={tabIndex} onChange={setTabIndex} colorScheme="blue">
        <TabList>
          <Tab>Generate</Tab>
          <Tab>History</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <GenerateTab onCreated={handleReportCreated} />
          </TabPanel>
          <TabPanel>
            <HistoryTab triggerReload={historyRefreshKey} />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default ComplianceViewer;
