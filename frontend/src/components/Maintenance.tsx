import { Wrench } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

/** Mesas module is temporarily under maintenance. */
export default function Maintenance() {
  return (
    <div className="mx-auto max-w-xl py-10" data-testid="tables-maintenance">
      <Card className="border-amber-200 bg-amber-50/40"><CardContent className="space-y-3 p-8">
        <span className="grid h-14 w-14 place-items-center rounded-2xl bg-amber-100 text-amber-700"><Wrench size={26} /></span>
        <h1 className="font-heading text-2xl font-semibold">Mesas em manutenção</h1>
        <p className="text-sm text-stone-600">Estamos melhorando o sistema de mesas. Ele volta em breve. Pedidos de balcão, entrega e WhatsApp funcionam normalmente.</p>
      </CardContent></Card>
    </div>
  );
}
