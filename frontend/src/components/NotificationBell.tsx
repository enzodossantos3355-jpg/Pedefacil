import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bell, ClipboardList, Headphones, Receipt } from "lucide-react";
import { toast } from "sonner";
import { apiGet } from "@/lib/api";
import { formatTime, type AppNotification } from "@/lib/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

const ICON = { new_order: ClipboardList, needs_human: Headphones, receipt: Receipt };
const SEEN_KEY = "pf_seen_notifications";

function beep() {
  try {
    const ctx = new AudioContext();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = 880;
    g.gain.setValueAtTime(0.15, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    o.connect(g).connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + 0.5);
  } catch { /* audio blocked until the user interacts */ }
}

/** Header bell: polls new orders, human-help requests and Pix receipts; rings + browser alert on new ones. */
export default function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState<string[]>(() => JSON.parse(localStorage.getItem(SEEN_KEY) || "[]"));
  const known = useRef<Set<string> | null>(null);
  const q = useQuery({ queryKey: ["notifications"], queryFn: () => apiGet<AppNotification[]>("/notifications"), refetchInterval: 15000 });
  const items = q.data ?? [];
  const unread = items.filter((n) => !seen.includes(n.id));

  useEffect(() => {
    if (!q.data) return;
    if (known.current) {
      const fresh = q.data.filter((n) => !known.current!.has(n.id));
      if (fresh.length) {
        beep();
        toast.info(fresh[0].title, { description: fresh[0].detail });
        if ("Notification" in window && Notification.permission === "granted") new Notification(`PedeFácil · ${fresh[0].title}`, { body: fresh[0].detail });
      }
    }
    known.current = new Set(q.data.map((n) => n.id));
  }, [q.data]);

  const onOpen = (v: boolean) => {
    setOpen(v);
    if ("Notification" in window && Notification.permission === "default") void Notification.requestPermission();
    if (!v) {
      const ids = items.map((n) => n.id);
      setSeen(ids);
      localStorage.setItem(SEEN_KEY, JSON.stringify(ids));
    }
  };

  return (
    <Popover open={open} onOpenChange={onOpen}>
      <PopoverTrigger className="relative rounded-lg p-2 text-stone-500 transition-colors hover:bg-stone-100" data-testid="notifications-button" aria-label="Notificações">
        <Bell size={19} />
        {unread.length > 0 && <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-[#C5533B] px-1 text-[10px] font-bold text-white" data-testid="notifications-count">{unread.length}</span>}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0" data-testid="notifications-panel">
        <div className="border-b border-stone-100 px-4 py-3 text-sm font-semibold">Notificações</div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 && <p className="px-4 py-8 text-center text-sm text-stone-400" data-testid="notifications-empty">Nada novo por aqui.</p>}
          {items.map((n) => {
            const Icon = ICON[n.kind];
            return (
              <button key={n.id} onClick={() => { onOpen(false); navigate(n.link); }} className={`flex w-full gap-3 border-b border-stone-50 px-4 py-3 text-left transition-colors hover:bg-stone-50 ${seen.includes(n.id) ? "" : "bg-[#fff7f4]"}`} data-testid={`notification-${n.kind}-${n.id}`}>
                <Icon size={16} className="mt-0.5 shrink-0 text-[#C5533B]" />
                <span className="min-w-0"><strong className="block truncate text-xs">{n.title}</strong><small className="block truncate text-[11px] text-stone-500">{n.detail}</small><small className="text-[10px] text-stone-400">{formatTime(n.created_at)}</small></span>
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
