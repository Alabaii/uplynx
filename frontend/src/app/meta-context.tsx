import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getMeta, type DeploymentMode, type Meta } from './api';

const MetaContext = createContext<Meta | null>(null);

export function MetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    let ignore = false;

    getMeta()
      .then((value) => {
        if (!ignore) {
          setMeta(value);
        }
      })
      .catch(() => {
        // meta недоступна — оставляем null (loading); UI организаций просто не показывается
      });

    return () => {
      ignore = true;
    };
  }, []);

  return <MetaContext.Provider value={meta}>{children}</MetaContext.Provider>;
}

export function useMeta(): Meta | null {
  return useContext(MetaContext);
}

export function useDeploymentMode(): DeploymentMode | null {
  return useContext(MetaContext)?.deployment_mode ?? null;
}
