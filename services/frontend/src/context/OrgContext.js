import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const OrgContext = createContext(null);

export const OrgProvider = ({ children }) => {
  const [activeOrg, setActiveOrg] = useState({ id: null, name: 'My Organization', is_msp: false });
  const [managedOrgs, setManagedOrgs] = useState([]);
  const [isMsp, setIsMsp] = useState(false);

  useEffect(() => {
    api.getMspOverview()
      .then((data) => {
        const orgs = data?.orgs || [];
        if (orgs.length > 0) {
          setManagedOrgs(orgs);
          setIsMsp(true);
          setActiveOrg({ id: orgs[0].id, name: orgs[0].name, is_msp: true });
          api.setActiveOrg(orgs[0].id);
        }
      })
      .catch(() => {
        // Non-MSP user or API not yet available — no-op, defaults are correct
      });
  }, []);

  const switchOrg = (orgId) => {
    const org = managedOrgs.find((o) => o.id === orgId);
    if (!org) return;
    setActiveOrg({ id: org.id, name: org.name, is_msp: true });
    api.setActiveOrg(orgId);
  };

  return (
    <OrgContext.Provider value={{ activeOrg, managedOrgs, isMsp, switchOrg }}>
      {children}
    </OrgContext.Provider>
  );
};

export const useOrg = () => {
  const context = useContext(OrgContext);
  if (!context) throw new Error('useOrg must be used within an OrgProvider');
  return context;
};

export default OrgContext;
