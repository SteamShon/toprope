CREATE TYPE order_status AS ENUM ('paid', 'shipped', 'refunded');

CREATE TABLE orders (
  id uuid PRIMARY KEY,
  status order_status NOT NULL,
  channel text CHECK (channel IN ('web', 'store')),
  total numeric NOT NULL
);
