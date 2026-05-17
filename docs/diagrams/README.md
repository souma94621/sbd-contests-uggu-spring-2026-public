# Диаграммы PlantUML

Исходники: `*.puml`. Сгенерированные изображения: `png/*.png`.

Сборка (нужен PlantUML и headless JVM при отсутствии дисплея):

```bash
make diagrams
```

Или вручную:

```bash
JAVA_TOOL_OPTIONS=-Djava.awt.headless=true plantuml -tpng -o png docs/diagrams/*.puml
```
