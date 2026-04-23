import { StrictMode, Suspense, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { router } from "./app/router";
import { useAuthStore } from "@/store/authStore";
import PageLoader from "@/components/PageLoader";
import "./styles/tokens.css";
import "./styles/global.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30,       // 30s
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * AppInitializer runs once on mount and restores the auth session from
 * sessionStorage before the router renders any protected routes.
 *
 * It blocks rendering until isInitialised=true so RequireAuth never sees
 * an intermediate state where the user looks logged out mid-refresh.
 */
function AppInitializer({ children }: { children: React.ReactNode }) {
  const init = useAuthStore((s) => s.init);
  const isInitialised = useAuthStore((s) => s.isInitialised);

  useEffect(() => {
    init();
  }, [init]);

  if (!isInitialised) return <PageLoader />;
  return <>{children}</>;
}

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppInitializer>
        <Suspense fallback={<PageLoader />}>
          <RouterProvider router={router} />
        </Suspense>
      </AppInitializer>
    </QueryClientProvider>
  </StrictMode>
);
