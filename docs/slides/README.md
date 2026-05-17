# Презентация (Beamer)

- Исходник: `presentation.tex`, тема: `lk-theme.tex`.
- Сборка PDF: [build_pdf.sh](build_pdf.sh) (нужны `xelatex`, шрифты DejaVu, пакеты `polyglossia`, `fontspec`, `beamer`).

```bash
cd docs/slides
chmod +x build_pdf.sh
./build_pdf.sh
```

В результате появляется `presentation.pdf`. Временные файлы LaTeX перечислены в [.gitignore](.gitignore) в этом каталоге.
