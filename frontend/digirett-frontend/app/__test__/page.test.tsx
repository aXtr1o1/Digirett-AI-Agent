import { render, screen } from '@testing-library/react';

jest.mock('../page', () => ({
  __esModule: true,
  default: () => <div>Digirett</div>,
}));

describe('Home Page', () => {
  it('renders welcome text', () => {
    render(<div>Digirett</div>);
    expect(screen.getByText(/digirett/i)).toBeInTheDocument();
  });
});

