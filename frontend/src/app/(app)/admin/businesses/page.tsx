"use client";

import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, errorText } from "@/lib/api/client";
import { useSession } from "@/lib/session";

export default function BusinessesPage() {
  const { user, businesses, selectBusiness, businessId } = useSession();
  const [name, setName] = useState("");
  const [ownerLogin, setOwnerLogin] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (user?.role !== "admin") return <Alert>Раздел доступен только администратору платформы.</Alert>;

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(null);
    const b = await api.POST("/api/v1/businesses", { body: { name } });
    if (b.error || !b.data) return setError(errorText(b.error));
    const u = await api.POST("/api/v1/users", {
      body: { login: ownerLogin, password: ownerPassword, role: "owner", business_id: b.data.id },
    });
    if (u.error) return setError(`Бизнес создан, собственник нет: ${errorText(u.error)}`);
    setDone(`Создан «${b.data.name}», собственник ${ownerLogin}. Обновите страницу, чтобы он появился в списке.`);
    setName("");
    setOwnerLogin("");
    setOwnerPassword("");
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Бизнесы</h1>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-2 sm:pt-2">
            <Table>
              <THead>
                <TR>
                  <TH>Название</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {businesses.map((b) => (
                  <TR key={b.id}>
                    <TD>{b.name}</TD>
                    <TD className="text-right">
                      {b.id === businessId ? (
                        <span className="text-sm text-muted-foreground">выбран</span>
                      ) : (
                        <Button variant="ghost" size="sm" onClick={() => selectBusiness(b.id)}>
                          Выбрать
                        </Button>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Новый бизнес</CardTitle>
            <CardDescription>Сразу с собственником, который даст согласие и загрузит данные.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={create} className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="bname">Название</Label>
                <Input id="bname" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ologin">Логин собственника</Label>
                <Input id="ologin" value={ownerLogin} onChange={(e) => setOwnerLogin(e.target.value)} required minLength={3} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="opass">Пароль собственника</Label>
                <Input id="opass" type="password" value={ownerPassword} onChange={(e) => setOwnerPassword(e.target.value)} required minLength={8} />
              </div>
              {error && <Alert variant="destructive">{error}</Alert>}
              {done && <Alert variant="success">{done}</Alert>}
              <Button type="submit">Создать</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
