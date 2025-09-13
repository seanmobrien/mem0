"use client";

import { Button } from "@/components/ui/button";
import { HiHome, HiMiniRectangleStack } from "react-icons/hi2";
import { RiApps2AddFill } from "react-icons/ri";
import { FiRefreshCcw } from "react-icons/fi";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CreateMemoryDialog } from "@/app/memories/components/CreateMemoryDialog";
import { useMemoriesApi } from "@/hooks/useMemoriesApi";
import Image from "next/image";
import { useStats } from "@/hooks/useStats";
import { useAppsApi } from "@/hooks/useAppsApi";
import { Settings, LogOut, User } from "lucide-react";
import { useConfig } from "@/hooks/useConfig";
import { useAuth } from "@/hooks/useAuth";
import { signOut } from "next-auth/react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

export function Navbar() {
  const pathname = usePathname();
  const { user, isLoading, isAuthenticated } = useAuth();

  const memoriesApi = useMemoriesApi();
  const appsApi = useAppsApi();
  const statsApi = useStats();
  const configApi = useConfig();

  // Define route matchers with typed parameter extraction
  const routeBasedFetchMapping: {
    match: RegExp;
    getFetchers: (params: Record<string, string>) => (() => Promise<any>)[];
  }[] = [
    {
      match: /^\/memory\/([^/]+)$/,
      getFetchers: ({ memory_id }) => [
        () => memoriesApi.fetchMemoryById(memory_id),
        () => memoriesApi.fetchAccessLogs(memory_id),
        () => memoriesApi.fetchRelatedMemories(memory_id),
      ],
    },
    {
      match: /^\/apps\/([^/]+)$/,
      getFetchers: ({ app_id }) => [
        () => appsApi.fetchAppMemories(app_id),
        () => appsApi.fetchAppAccessedMemories(app_id),
        () => appsApi.fetchAppDetails(app_id),
      ],
    },
    {
      match: /^\/memories$/,
      getFetchers: () => [memoriesApi.fetchMemories],
    },
    {
      match: /^\/apps$/,
      getFetchers: () => [appsApi.fetchApps],
    },
    {
      match: /^\/$/,
      getFetchers: () => [statsApi.fetchStats, memoriesApi.fetchMemories],
    },
    {
      match: /^\/settings$/,
      getFetchers: () => [configApi.fetchConfig],
    },
  ];

  const getFetchersForPath = (path: string) => {
    for (const route of routeBasedFetchMapping) {
      const match = path.match(route.match);
      if (match) {
        if (route.match.source.includes("memory")) {
          return route.getFetchers({ memory_id: match[1] });
        }
        if (route.match.source.includes("app")) {
          return route.getFetchers({ app_id: match[1] });
        }
        return route.getFetchers({});
      }
    }
    return [];
  };

  const handleRefresh = async () => {
    const fetchers = getFetchersForPath(pathname);
    await Promise.allSettled(fetchers.map((fn) => fn()));
  };

  const isActive = (href: string) => {
    if (href === "/") return pathname === href;
    return pathname.startsWith(href.substring(0, 5));
  };

  const activeClass = "bg-zinc-800 text-white border-zinc-600";
  const inactiveClass = "text-zinc-300";

  return (
    <header className="sticky top-0 z-50 w-full border-b border-zinc-800 bg-zinc-950/95 backdrop-blur supports-[backdrop-filter]:bg-zinc-950/60">
      <div className="container flex h-14 items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <Image src="/logo.svg" alt="OpenMemory" width={26} height={26} />
          <span className="text-xl font-medium">OpenMemory</span>
        </Link>
        <div className="flex items-center gap-2">
          <Link href="/">
            <Button
              variant="outline"
              size="sm"
              className={`flex items-center gap-2 border-none ${
                isActive("/") ? activeClass : inactiveClass
              }`}
            >
              <HiHome />
              Dashboard
            </Button>
          </Link>
          <Link href="/memories">
            <Button
              variant="outline"
              size="sm"
              className={`flex items-center gap-2 border-none ${
                isActive("/memories") ? activeClass : inactiveClass
              }`}
            >
              <HiMiniRectangleStack />
              Memories
            </Button>
          </Link>
          <Link href="/apps">
            <Button
              variant="outline"
              size="sm"
              className={`flex items-center gap-2 border-none ${
                isActive("/apps") ? activeClass : inactiveClass
              }`}
            >
              <RiApps2AddFill />
              Apps
            </Button>
          </Link>
          <Link href="/settings">
            <Button
              variant="outline"
              size="sm"
              className={`flex items-center gap-2 border-none ${
                isActive("/settings") ? activeClass : inactiveClass
              }`}
            >
              <Settings />
              Settings
            </Button>
          </Link>
        </div>
        <div className="flex items-center gap-4">
          <Button
            onClick={handleRefresh}
            variant="outline"
            size="sm"
            className="border-zinc-700/50 bg-zinc-900 hover:bg-zinc-800"
          >
            <FiRefreshCcw className="transition-transform duration-300 group-hover:rotate-180" />
            Refresh
          </Button>
          <CreateMemoryDialog />
          
          {/* User Profile Dropdown */}
          {isAuthenticated && user && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={user.image || ''} alt={user.name || 'User'} />
                    <AvatarFallback>
                      {user.name?.charAt(0).toUpperCase() || user.email?.charAt(0).toUpperCase() || 'U'}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56" align="end" forceMount>
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium leading-none">{user.name || 'User'}</p>
                    <p className="text-xs leading-none text-muted-foreground">
                      {user.email}
                    </p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link href="/settings" className="cursor-pointer">
                    <Settings className="mr-2 h-4 w-4" />
                    <span>Settings</span>
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem 
                  className="cursor-pointer"
                  onClick={() => signOut({ callbackUrl: '/auth/signin' })}
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Log out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </header>
  );
}
