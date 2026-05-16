import { PluginAuthProvider } from '@/hooks/use-plugin-auth'

export default function PluginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="dark bg-background flex h-screen w-screen overflow-hidden">
      <PluginAuthProvider>
        {children}
      </PluginAuthProvider>
    </div>
  );
}
