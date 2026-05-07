"use client";

import AdminDashboard from "../../../../components/AdminDashboard";
import AdminSubNav from "../../../../components/AdminSubNav";

export default function AdminUsersPage() {
  return (
    <div className="page-shell">
      <section className="page-header">
        <h1 className="page-title">Admin</h1>
        <p className="page-subtitle">User lifecycle, roles, activation state, and password resets.</p>
      </section>
      <AdminSubNav />
      <AdminDashboard />
    </div>
  );
}
