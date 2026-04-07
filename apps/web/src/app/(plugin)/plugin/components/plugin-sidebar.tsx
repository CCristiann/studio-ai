"use client";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  MessageSquare,
  Globe,
  Zap,
  HelpCircle,
  Settings,
  LogOut,
} from "lucide-react";

export type PanelId = "chat" | "connection" | "presets" | "settings" | "help";

const topItems: { id: PanelId; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "connection", label: "Connection", icon: Globe },
  { id: "presets", label: "Quick Actions", icon: Zap },
];

const bottomItems: { id: PanelId; label: string; icon: typeof HelpCircle }[] = [
  { id: "help", label: "Help", icon: HelpCircle },
  { id: "settings", label: "Settings", icon: Settings },
];

export function PluginSidebar({
  activePanel,
  onPanelChange,
  onSignOut,
  connectionStatus,
  panelContent,
}: {
  activePanel: PanelId;
  onPanelChange: (panel: PanelId) => void;
  onSignOut: () => void;
  connectionStatus: "connected" | "partial" | "disconnected";
  panelContent: React.ReactNode;
}) {
  const { toggleSidebar, state } = useSidebar();

  const handleClick = (panelId: PanelId) => {
    if (state === "collapsed") {
      onPanelChange(panelId);
      toggleSidebar();
    } else if (activePanel === panelId) {
      toggleSidebar();
    } else {
      onPanelChange(panelId);
    }
  };

  const statusColor =
    connectionStatus === "connected"
      ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]"
      : connectionStatus === "partial"
        ? "bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.4)]"
        : "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]";

  const renderItem = (item: { id: PanelId; label: string; icon: typeof MessageSquare }) => (
    <SidebarMenuItem key={item.id}>
      <SidebarMenuButton
        isActive={activePanel === item.id}
        onClick={() => handleClick(item.id)}
        className="relative"
      >
        <item.icon className="w-5 h-5" />
        <span className="group-data-[collapsible=icon]:hidden">
          {item.label}
        </span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );

  return (
    <Sidebar
      collapsible="icon"
      variant="sidebar"
      className="border-r-0 bg-[#080808]"
    >
      <SidebarHeader className="flex items-center justify-center py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-gradient-to-b from-neutral-200 to-neutral-400 text-[15px] font-extrabold text-black shadow-md">
          S
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="flex justify-center group-data-[collapsible=icon]:items-center">
              {topItems.map(renderItem)}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Panel content — hidden when collapsed to icon mode */}
        <SidebarGroup className="group-data-[collapsible=icon]:hidden flex-1 overflow-y-auto border-l border-white/[0.04]">
          <div className="px-4 py-3.5 border-b border-white/[0.04]">
            <div className="text-[13px] font-semibold text-[#e5e5e5] tracking-tight">
              {activePanel === "chat" && "Chats"}
              {activePanel === "connection" && "Connection"}
              {activePanel === "presets" && "Quick Actions"}
              {activePanel === "settings" && "Settings"}
              {activePanel === "help" && "Help"}
            </div>
          </div>
          {panelContent}
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu className="flex justify-center group-data-[collapsible=icon]:items-center">
          {bottomItems.map(renderItem)}
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger className="flex w-full items-center gap-2 rounded-md p-2 group-data-[collapsible=icon]:!size-8 group-data-[collapsible=icon]:!p-2 hover:bg-sidebar-accent">
                <div className="relative shrink-0">
                  <div className="flex size-5 items-center justify-center rounded-full bg-gradient-to-b from-indigo-400 to-violet-500 text-[8px] font-bold text-white shadow-md">
                    U
                  </div>
                  <div
                    className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-[#080808] ${statusColor}`}
                  />
                </div>
                <span className="group-data-[collapsible=icon]:hidden text-sm">
                  Account
                </span>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="right" align="end">
                <DropdownMenuItem onClick={onSignOut}>
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar >
  );
}
