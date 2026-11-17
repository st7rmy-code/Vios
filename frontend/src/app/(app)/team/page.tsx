"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { ConfirmDialog } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { api, businessParam, errorText, type Schemas } from "@/lib/api/client";
import { dateTime } from "@/lib/format";
import { ROLE_LABEL, useSession } from "@/lib/session";

export default function TeamPage() {
  const { user } = useSession();
  const [users, setUsers] = useState<Schemas["UserOut"][]>([]);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"executor" | "owner">("executor");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET("/api/v1/users");
    setUsers(data ?? []);
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const { error } = await api.POST("/api/v1/users", { body: { login, password, role, ...businessParam() } });
    if (error) return setError(errorText(error));
    setLogin("");
    setPassword("");
    load();
  }

  async function deactivate(id: string) {
    const { error } = await api.POST("/api/v1/users/{user_id}/deactivate", { params: { path: { user_id: id } } });
    if (error) return setError(errorText(error));
    load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Команда</h1>
        <p className="text-sm text-muted-foreground">Исполнители видят только тестовую группу и действие, без денег и контроля.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="pt-2 sm:pt-2">
            <Table>
              <THead>
                <TR>
                  <TH>Логин</TH>
                  <TH>Роль</TH>
                  <TH className="hidden sm:table-cell">Последний вход</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {users.map((u) => (
                  <TR key={u.id}>
                    <TD>{u.login}</TD>
                    <TD>
                      {ROLE_LABEL[u.role]} {!u.is_active && <Badge variant="secondary">отключён</Badge>}
                    </TD>
                    <TD className="hidden sm:table-cell">{u.last_login_at ? dateTime(u.last_login_at) : "—"}</TD>
                    <TD className="text-right">
                      {u.is_active && u.id !== user?.id && u.role !== "admin" && (
                        <ConfirmDialog
                          trigger={
                            <Button variant="ghost" size="sm">
                              Отключить
                            </Button>
                          }
                          title={`Отключить ${u.login}?`}
                          description="Пользователь больше не сможет войти. Его действия останутся в журнале."
                          confirm="Отключить"
                          onConfirm={() => deactivate(u.id)}
                        />
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
            <CardTitle>Добавить</CardTitle>
            <CardDescription>Логин и пароль передайте человеку сами.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={add} className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="ulogin">Логин</Label>
                <Input id="ulogin" value={login} onChange={(e) => setLogin(e.target.value)} required minLength={3} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="upass">Пароль, от 8 символов</Label>
                <Input id="upass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
              </div>
              {user?.role === "admin" && (
                <div className="space-y-2">
                  <Label htmlFor="urole">Роль</Label>
                  <Select id="urole" value={role} onChange={(e) => setRole(e.target.value as "executor" | "owner")}>
                    <option value="executor">Исполнитель</option>
                    <option value="owner">Собственник</option>
                  </Select>
                </div>
              )}
              {error && <Alert variant="destructive">{error}</Alert>}
              <Button type="submit">Добавить</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
