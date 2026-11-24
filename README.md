# Gestão de Leitura

Sistema web para catalogar e acompanhar leituras de **livros** e **web novels**.
Projeto acadêmico da disciplina de Elicitação e Análise de Requisitos (IFMT).

## Requisitos

- Python 3.14 (testado com 3.14.6)
- Django 6.1.3
- Pillow 13.0.0 (upload de capas)

As versões verificadas estão em `requirements.txt`.

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

Acesse `http://127.0.0.1:8000/`. O ambiente virtual (`virtual/`) é ignorado pelo
Git e não deve ser versionado.

## Configuração por ambiente

O projeto funciona localmente sem variáveis de ambiente. Para produção ou para
alterar o comportamento local, configure:

| Variável | Padrão local | Descrição |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Use `False` em produção. |
| `DJANGO_SECRET_KEY` | chave de desenvolvimento | Obrigatória quando `DJANGO_DEBUG=False`. |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost,testserver` | Lista de hosts separada por vírgulas. |
| `DJANGO_PDF_STORAGE_ROOT` | `privado/pdfs` | Pasta privada dos PDFs, fora de `midia/`. |
| `DJANGO_PDF_MAX_SIZE_MB` | `20` | Tamanho máximo de cada PDF, em MB. |

Exemplo no PowerShell:

```powershell
$env:DJANGO_DEBUG = "False"
$env:DJANGO_SECRET_KEY = "coloque-aqui-uma-chave-longa-e-secreta"
$env:DJANGO_ALLOWED_HOSTS = "seudominio.com,www.seudominio.com"
$env:DJANGO_PDF_STORAGE_ROOT = "D:\dados-privados\pdfs"
$env:DJANGO_PDF_MAX_SIZE_MB = "30"
python manage.py runserver
```

Com `DJANGO_DEBUG=False`, a aplicação não inicia sem `DJANGO_SECRET_KEY`. Em
desenvolvimento, uma chave insegura de fallback é usada apenas para facilitar a
execução local. Em produção, mantenha `privado/pdfs` (ou o diretório configurado
em `DJANGO_PDF_STORAGE_ROOT`) fora da pasta servida pelo servidor web.

## Perfis de usuário

| Papel | Permissões |
|---|---|
| `LEITOR` | Usa o catálogo, acompanha leituras, gerencia as próprias estantes e avalia obras ativas. Não envia obras. |
| `MODERADOR` | Envia obras e consulta a fila em `/moderacao/`. Pode editar ou excluir apenas as próprias obras pendentes. Não aprova nem rejeita obras. |
| `ADMIN` | Aprova ou rejeita obras pendentes, edita ou exclui qualquer obra e pode editar ou excluir submissões de outros usuários. |

O cadastro público sempre cria uma conta `LEITOR`. O papel é concedido depois
por um administrador.

## Fluxo de cadastro, envio e aprovação

1. O visitante cria uma conta em `/registro/`; o perfil é criado como `LEITOR`.
2. Um administrador promove a conta para `MODERADOR` ou `ADMIN` quando necessário.
3. Apenas `MODERADOR` e `ADMIN` acessam `/adicionar_obra/` e enviam obras.
4. Toda obra enviada nasce com o estado **Pendente**, inclusive quando enviada por
   um administrador.
5. Moderadores e administradores veem a fila em `/moderacao/`.
6. Apenas administradores aprovam ou rejeitam. A aprovação muda o estado para
   **Ativa** e limpa o motivo da rejeição; a rejeição exige um motivo e muda para
   **Rejeitada**.
7. Somente obras **Ativas** aparecem no catálogo público. Obras pendentes ou
   rejeitadas ficam visíveis apenas para quem as enviou e para a moderação.
8. O autor acompanha o status e o eventual motivo da rejeição em **Minhas
   submissões**, no início.

## Papel ADMIN do site e acesso ao /admin/ do Django

São dois controles diferentes:

- O papel `ADMIN` do site fica em `Perfil.papel` e controla as ações da aplicação:
  aprovar/rejeitar obras, editar/excluir qualquer obra e acessar o painel de
  moderação.
- O `/admin/` do Django exige `is_staff`/`is_superuser` e as permissões nativas do
  Django. Ter o papel `ADMIN` no site não concede, por si só, acesso ao `/admin/`.

Superusuários recebem automaticamente o papel `ADMIN` do site pelo sinal de
criação de perfil. Para promover um usuário, acesse `/admin/` com uma conta que
tenha permissão, abra **Perfis**, altere o campo **Papel** e salve. O admin do
Django também restringe a edição de obras ao papel `ADMIN` do site, impedindo que
um moderador publique obras por esse caminho.

## Acompanhamento de leitura

- Na página de uma obra ativa, o leitor informa o progresso inicial e clica em **Começar a acompanhar**.
- O progresso pode ser atualizado a qualquer momento; ao atingir o total de páginas/capítulos, a leitura é concluída automaticamente.
- Se o progresso for reduzido depois da conclusão, a leitura volta para **Lendo**.
- O início mostra **Continuar a leitura** e a página **Minhas leituras** separa as obras em andamento das concluídas.

## Leitura de PDF (obras do formato Livro)

- O PDF é opcional e só pode ser anexado na **edição** de uma obra do formato
  **Livro**; o formulário de cadastro não exibe nem aceita o campo.
- O envio é validado pela extensão `.pdf`, pela assinatura do arquivo e pelo
  limite configurado em `DJANGO_PDF_MAX_SIZE_MB` (20 MB por padrão).
- O arquivo fica em `privado/pdfs`, fora de `midia/`, sem URL pública. O acesso
  passa por `/ler_pdf/<id>/` e respeita as mesmas regras da página da obra:
  obras ativas são públicas; pendentes/rejeitadas ficam restritas ao autor e à
  moderação.
- A resposta é entregue inline, com `Cache-Control: private, no-store` e
  `X-Content-Type-Options: nosniff`.
- Ao trocar uma obra de Livro para Web Novel, o PDF existente permanece
  armazenado, mas deixa de aparecer e de ser servido. Novos uploads de PDF em
  Web Novel são rejeitados.
- O admin do Django continua podendo cadastrar e gerenciar PDFs livremente.

## Capítulos de Web Novels

- Obras do formato **Web Novel** exibem a lista de capítulos na página de
  detalhes, com a contagem de capítulos disponíveis em relação ao total.
- Usuários autorizados gerenciam capítulos pela própria página da obra. O
  `ADMIN` gerencia qualquer obra; o `MODERADOR` gerencia apenas as próprias
  obras pendentes.
- Cada capítulo tem número único por obra, título e conteúdo. O conteúdo é
  exibido como texto escapado e preserva quebras de linha.
- A leitura oferece navegação para capítulo anterior, próximo e retorno à obra.
- O progresso de leitura continua usando o total de páginas/capítulos informado
  na obra; a quantidade de capítulos publicados é apenas informativa.

## Estantes personalizadas

- Em **Estantes**, o leitor cria, renomeia e exclui estantes pessoais; o nome deve ser único entre as estantes do mesmo usuário.
- Obras ativas podem ser adicionadas pela página da obra ou pela busca dentro da estante, e removidas a qualquer momento.
- A página inicial mostra um resumo das estantes; cada estante lista apenas obras ativas.
- As estantes são privadas: cada usuário acessa somente as próprias.

## Avaliações e comentários

- Na página de uma obra ativa, usuários autenticados dão uma nota de 1 a 5 e podem escrever um comentário opcional.
- Cada usuário tem uma avaliação por obra, que pode ser atualizada ou removida; a página mostra a média e as avaliações públicas.
- Apenas obras ativas recebem e exibem avaliações.

## Estatísticas e acessibilidade

- O início exibe um resumo com obras ativas, leituras em andamento/concluídas, avaliações e estantes do usuário.
- A interface inclui link **Pular para o conteúdo**, rótulos ARIA nas avaliações, barras de progresso acessíveis e foco visível.

## Testes

Execute com o banco de testes do Django:

```powershell
python manage.py test sistema
```

Os testes usam um banco de testes isolado e não alteram o `db.sqlite3` original.
A suíte cobre:

- GET e POST (válido e inválido) de `/adicionar_obra/`.
- Cadastro público criando perfil `LEITOR`.
- Uso do catálogo, leituras, estantes e avaliações por leitor.
- Permissões de leitor, moderador e administrador.
- Submissão sempre pendente, inclusive por administrador.
- Aprovação, rejeição com motivo e bloqueio de decisões para obras não pendentes.
- Catálogo exibindo a obra somente após aprovação.
- Edição/exclusão de obras ativas e de submissões de terceiros restrita ao administrador.
- Moderador editando/excluindo apenas as próprias obras pendentes.
- Exibição condicional dos botões de editar/excluir.
- Restrição do modelo `Obra` no admin do Django ao papel `ADMIN` do site.
- Cadastro sem PDF e rejeição de POST manipulado com PDF.
- Upload, validação, armazenamento privado e acesso a PDFs de livros.
- Acesso a PDFs por estado da obra e permissões de autor, moderação e leitor.
- Criação, edição, exclusão e leitura de capítulos de Web Novels.
- Permissões de capítulos para `ADMIN`, `MODERADOR`, `LEITOR` e visitantes.
- Unicidade e validação positiva do número do capítulo.
- Navegação entre capítulos e preservação de quebras de linha no conteúdo.

## Funcionalidades implementadas

- Cadastro, login e logout; cadastro público sempre cria `LEITOR`.
- Model `Perfil` com papéis `LEITOR`, `MODERADOR` e `ADMIN`.
- Envio de obras exclusivo de `MODERADOR` e `ADMIN`; toda submissão nasce **Pendente**.
- Fila de moderação acessível a moderadores; aprovação/rejeição exclusiva de `ADMIN`.
- Regras de edição/exclusão: administrador gerencia qualquer obra; moderador gerencia apenas as próprias pendentes; obras ativas são protegidas.
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
- Leitura de PDF privado para livros, com upload na edição e validação de formato, assinatura e tamanho.
- Gestão de capítulos de Web Novels, com leitura, navegação, unicidade de número e permissões por estado da obra.
- Admin configurado para perfis, gêneros, obras, capítulos, leituras, estantes e avaliações, com restrição de obras ao `ADMIN` do site.
- Testes automatizados de submissão, moderação, permissões, PDFs e capítulos.

## Próximas fases

Nenhuma fase planejada; o projeto está completo.

## Estrutura

```
leitura/        Configurações e URLs do projeto
sistema/        Models, views, forms, admin, sinais e permissões
templates/      Templates compartilhados e do app
midia/          Capas enviadas (dados de exemplo)
privado/pdfs/   PDFs privados (gerados em execução, ignorados pelo Git)
db.sqlite3      Banco SQLite com dados de exemplo
```

O `db.sqlite3` e a pasta `midia/` são mantidos no repositório neste projeto
acadêmico para preservar os dados de exemplo. A pasta `privado/` é ignorada pelo
Git e não deve ser servida publicamente.

A migração `sistema.0014_obra_arquivo_pdf_capitulo` adiciona o campo privado de
PDF e a tabela de capítulos. Execute `python manage.py migrate` após atualizar
o projeto.
