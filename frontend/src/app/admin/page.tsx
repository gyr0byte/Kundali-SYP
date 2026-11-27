import type { Metadata } from "next";
import { AdminWorkspace } from "@/components/admin/AdminWorkspace";

export const metadata: Metadata = {
  title: "Admin console | Kundali",
  robots: { index: false, follow: false },
};

export default function AdminDashboard() {
  return <AdminWorkspace />;
}
