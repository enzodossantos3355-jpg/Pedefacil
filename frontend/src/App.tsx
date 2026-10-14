import { Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import AppShell from "@/components/AppShell";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import Pedidos from "@/pages/Pedidos";
import DayGate from "@/components/DayGate";
import Produtos from "@/pages/Produtos";
import Clientes from "@/pages/Clientes";
import Atendimento from "@/pages/Atendimento";
import Relatorios from "@/pages/Relatorios";
import Configuracoes from "@/pages/Configuracoes";
import Armazenamento from "@/pages/Armazenamento";
import Planos, { PaymentResult } from "@/pages/Planos";
import Suporte from "@/pages/Suporte";
import Master from "@/pages/Master";
import Mesas from "@/pages/Mesas";
import Equipe from "@/pages/Equipe";
import FeatureGate from "@/components/FeatureGate";

// One <Route> per page in src/pages; BrowserRouter already wraps this in main.tsx.
export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/master" element={<Master />} />
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/pedidos" element={<DayGate><Pedidos /></DayGate>} />
          <Route path="/produtos" element={<Produtos />} />
          <Route path="/clientes" element={<Clientes />} />
          <Route path="/atendimento" element={<FeatureGate feature="whatsapp_ia"><DayGate><Atendimento /></DayGate></FeatureGate>} />
          <Route path="/mesas" element={<FeatureGate feature="mesas"><DayGate><Mesas /></DayGate></FeatureGate>} />
          <Route path="/equipe" element={<Equipe />} />
          <Route path="/planos" element={<Planos />} />
          <Route path="/suporte" element={<Suporte />} />
          <Route path="/payment/success" element={<PaymentResult />} />
          <Route path="/payment/cancel" element={<PaymentResult />} />
          <Route path="/relatorios" element={<Relatorios />} />
          <Route path="/configuracoes" element={<Configuracoes />} />
          <Route path="/armazenamento" element={<Armazenamento />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      <Toaster richColors />
    </>
  );
}
