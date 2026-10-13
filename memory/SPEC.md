# Marmita Hub — Especificação viva

## Produto
Plataforma em português do Brasil para operação de restaurantes, marmitarias e delivery. A experiência preserva a linguagem visual do Feijoada/Marmita Hub: fundo quente, sidebar terrosa, terracota como ação primária, dados densos e cards discretos.

## Rotas e fluxos
- `/login` e `/register`: entrada de administrador/atendente usando sessão httpOnly.
- `/dashboard`: faturamento, pedidos ativos, caixa do dia e pedidos recentes.
- `/pedidos`: filtros por status, busca, criação no balcão, edição, avanço de status e exclusão.
- `/produtos`: cadastro, edição, preço, categoria e disponibilidade do cardápio.
- `/clientes`: agenda, busca, cadastro, edição e histórico resumido.
- `/atendimento`: lista de conversas e janela de mensagens preparada para WhatsApp; integração externa fica para fase posterior.
- `/relatorios`: faturamento, pagamentos, itens mais vendidos e área preparada para análise automatizada.
- `/armazenamento`: abertura/fechamento de caixa e fechamentos arquivados; ações de backup ficam preparadas.
- `/configuracoes`: endereço, horários, Pix, regras operacionais e áreas preparadas para canais/IA.

## Dados
MongoDB collections: `users`, `sessions`, `orders`, `products`, `customers`, `store_settings`, `delivery_zones`, `day_status`, `day_closes`, `chats`.
Pedidos usam status `Em Análise`, `Novo`, `Em Preparo`, `Pronto`, `Em Entrega`, `Concluído`, `Cancelado`. IDs são strings.

## Papéis
`admin` e `atendente` são aceitos no cadastro/login. A sessão usa cookie httpOnly. Credenciais de demonstração estão em `memory/test_credentials.md`.

## Integrações
WhatsApp, IA, exportação/importação completa de backup e impressão são áreas preparadas, mas não conectadas nesta fase conforme aprovado.