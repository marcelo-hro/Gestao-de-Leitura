# Gestão de Leitura

Projeto acadêmico do IFMT para catalogar livros e web novels e acompanhar o progresso de leitura. O sistema foi feito com Python, Django e SQLite.

- Consulte o catálogo, crie estantes e avalie obras.
- Registre o progresso dos livros e abra o PDF quando houver um anexo.
- Leia web novels por capítulo e acompanhe o que já leu.
- Moderadores podem enviar obras para aprovação. Administradores podem publicá-las diretamente. Usuários autorizados podem organizar capítulos em volumes e importar capítulos de arquivos EPUB.

## Como rodar no Windows

1. Instale o **Python 3.14**. Se estiver usando o arquivo RAR, extraia-o primeiro.
2. No VS Code, abra a pasta que contém `manage.py` e `requirements.txt`.
3. Abra o terminal do VS Code e execute os comandos abaixo, um por vez.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Os comandos usam diretamente o Python do ambiente virtual, então você pode executá-los no PowerShell sem ativar o ambiente.

Abra [http://127.0.0.1:8000/](http://127.0.0.1:8000/) no navegador. Para parar o servidor, pressione `Ctrl+C` no terminal.

## Contas e administração

Na página inicial, clique em **Criar conta** para usar o sistema como leitor.

Para criar uma conta de administrador, abra outro terminal na mesma pasta e execute o comando abaixo.

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Preencha os dados solicitados e entre em [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/). Em **Perfis**, você pode alterar o papel de uma conta para **Moderador**.

## Banco de dados e PDFs

O banco SQLite é local. Se o projeto estiver sem o banco de exemplo, o catálogo começa vazio. Os PDFs anexados ficam em `privado/pdfs/`. Se essa pasta estiver ausente, você pode anexar os PDFs novamente na tela **Editar obra**.