export default function PluginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="dark flex h-screen w-screen overflow-hidden bg-[#0a0a0a]">
      {children}
    </div>
  );
}
