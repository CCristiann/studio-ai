import { PluginAuthProvider } from '@/hooks/use-plugin-auth'

export default function PluginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="dark bg-background fixed inset-0 flex overflow-hidden">
      <PluginAuthProvider>
        {children}
      </PluginAuthProvider>
    </div>
  );
}
