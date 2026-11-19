# Gestão de Leitura

Sistema web para catalogar e acompanhar leituras de **livros** e **web novels**.
Projeto acadêmico da disciplina de Elicitação e Análise de Requisitos (IFMT).

## Requisitos

- Python 3.14+
- Django 6.1
- Pillow (upload de capas)

## Como executar

```powershell
# 1. Criar e ativar o ambiente virtual
python -m venv virtual
.\virtual\Scripts\Activate.ps1

# 2. Instalar as dependências
pip install -r requirements.txt

# 3. Aplicar as migrações
python manage.py migrate

# 4. Criar um superusuário (caso ainda não exista)
python manage.py createsuperuser

# 5. Rodar o servidor
python manage.py runserver
```

Acesse `http://127.0.0.1:8000/`.

## Perfis de usuário

| Papel | Permissões |
|---|---|
| `LEITOR` | Registra-se, consulta o catálogo, submete obras para moderação, acompanha o progresso das leituras, organiza obras em estantes, avalia obras e vê o status das próprias submissões. |
| `MODERADOR` | Aprova/rejeita obras, acessa o painel de moderação e edita metadados do catálogo. |
| `ADMIN` | Todas as permissões, incluindo o admin do Django. |

## Fluxo de submissão e moderação

1. Um leitor autenticado envia uma obra; ela fica com o estado **Pendente**.
2. Moderadores e administradores veem a obra no menu **Moderação** e podem aprová-la ou rejeitá-la (com motivo).
3. Obras **Ativas** aparecem no catálogo público. Obras pendentes ou rejeitadas ficam visíveis apenas para quem as enviou e para a moderação.
4. O autor acompanha o status e o eventual motivo da rejeição em **Minhas submissões**, no início.

## Acompanhamento de leitura

- Na página de uma obra ativa, o leitor informa o progresso inicial e clica em **Começar a acompanhar**.
- O progresso pode ser atualizado a qualquer momento; ao atingir o total de páginas/capítulos, a leitura é concluída automaticamente.
- Se o progresso for reduzido depois da conclusão, a leitura volta para **Lendo**.
- O início mostra **Continuar a leitura** e a página **Minhas leituras** separa as obras em andamento das concluídas.

## Estantes personalizadas

- Em **Estantes**, o leitor cria, renomeia e exclui estantes pessoais; o nome deve ser único entre as estantes do mesmo usuário.
- Obras ativas podem ser adicionadas pela página da obra ou pela busca dentro da estante, e removidas a qualquer momento.
- A página inicial mostra um resumo das estantes; cada estante lista apenas obras ativas.
- As estantes são privadas: cada usuário acessa somente as próprias.

## Avaliações e comentários

- Na página de uma obra ativa, leitores autenticados dão uma nota de 1 a 5 e podem escrever um comentário opcional.
- Cada usuário tem uma avaliação por obra, que pode ser atualizada ou removida; a página mostra a média e as avaliações públicas.
- Apenas obras ativas recebem e exibem avaliações.

## Estatísticas e acessibilidade

- O início exibe um resumo com obras ativas, leituras em andamento/concluídas, avaliações e estantes do usuário.
- A interface inclui link **Pular para o conteúdo**, rótulos ARIA nas avaliações, barras de progresso acessíveis e foco visível.

Para promover um usuário:

1. Acesse `/admin/`.
2. Abra **Perfis**.
3. Altere o campo **Papel** e salve.

Superusuários recebem automaticamente o papel `ADMIN`.

## Funcionalidades implementadas (Fases 1 a 6)

- Cadastro, login e logout de leitores.
- Model `Perfil` com papéis `LEITOR`, `MODERADOR` e `ADMIN`.
- Permissões: apenas moderadores/admin editam, excluem e moderam obras.
- Submissão de obras por leitores com estado **Pendente**; publicação imediata por moderadores.
- Painel de moderação com aprovação/rejeição e registro do motivo.
- Catálogo público apenas com obras ativas, com busca por título, autor, gênero e sinopse e paginação.
- Página de detalhes com sinopse, status de moderação e motivo de rejeição (para o autor e a moderação).
- Acompanhamento de leitura com progresso inicial, atualização, conclusão automática e reabertura.
- Dashboard com destaques, adições recentes, "Continuar a leitura" e "Minhas submissões".
- Página "Minhas leituras" com obras em andamento e concluídas, incluindo barras e percentuais de progresso.
- Estantes personalizadas com criação, edição, exclusão, inclusão/remoção de obras e busca de candidatas.
- Resumo de estantes no dashboard e seção "Suas estantes" na página da obra.
- Avaliações com nota de 1 a 5, comentário opcional, média e edição/remoção pelo autor.
- Estatísticas pessoais no dashboard.
- Acessibilidade: link "Pular para o conteúdo", ARIA em avaliações e barras de progresso, labels e foco visível.
- Exclusão de obra com confirmação via POST.
- Templates unificados em `base.html`, com mensagens de sucesso/erro.
- Admin configurado para perfis, gêneros, obras, leituras, estantes e avaliações.
- Testes de perfil, autenticação, permissões, catálogo, submissão, moderação, paginação, leitura, estantes, avaliações, estatísticas, acessibilidade e fluxo completo.

## Próximas fases

Nenhuma fase planejada; o projeto está completo.

## Estrutura

```
leitura/        Configurações e URLs do projeto
sistema/        Models, views, forms, admin, sinais e permissões
templates/      Templates compartilhados e do app
midia/          Capas enviadas (dados de exemplo)
db.sqlite3      Banco SQLite com dados de exemplo
```
