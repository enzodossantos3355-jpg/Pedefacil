import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import AuthCallback from "@/components/AuthCallback";
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
import Maintenance from "@/components/Maintenance";
import Entregadores from "@/pages/Entregadores";
import Equipe from "@/pages/Equipe";
import FeatureGate from "@/components/FeatureGate";

// One <Route> per page in src/pages; BrowserRouter already wraps this in main.tsx.
export default function App() {
  const location = useLocation(); // reactive hash: Google OAuth returns with #session_id=...
  if (location.hash.includes("session_id=")) return <><AuthCallback /><Toaster richColors /></>;
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
          <Route path="/entregadores" element={<FeatureGate feature="motoboys"><Entregadores /></FeatureGate>} />
          <Route path="/mesas" element={<Maintenance />} />
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
