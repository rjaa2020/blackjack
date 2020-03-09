from blackjack.classes.hand import Hand
from blackjack.exc import InsufficientBankrollError
from blackjack.utils import float_response, get_user_input, max_retries_exit


class Player:

    all_ = []

    # NOTE: If ever refactoring to allow many Players at a Table, this class should belong to a Table
    #       (i.e. many to one relationship Player to Table) and thus define a table attribute here.
    def __init__(self, name):
        self.name = name
        Player.all_.append(self)

    def __str__(self):
        return f"Player: {self.name}"

    def hands(self):
        return [hand for hand in Hand.all_ if hand.player == self]

    def discard_hands(self):
        # TODO: Delete the actual object entirely so we won't have Hand.all_ growing forever?
        for hand in self.hands():
            hand.player = None


class Gambler(Player):
    
    def __init__(self, name, bankroll=0, auto_wager=0):
        super().__init__(name)
        self.bankroll = bankroll
        self.auto_wager = auto_wager

        # Player is finished if they have set their auto_wager to $0 or if they are out of money
        self.is_finished = lambda: self.auto_wager == 0 or self.bankroll == 0

    def __str__(self):
        return super().__str__() + f" | Bankroll: ${self.bankroll}"

    def first_hand(self):
        # Helper method for action that happens on the initial hand dealt to the gambler
        return self.hands()[0]

    def payout(self, amount, message):
        self._add_bankroll(amount)
        print(message)

    def _add_bankroll(self, amount):
        self.bankroll += amount

    def _subtract_bankroll(self, amount):
        if self.bankroll < amount:
            raise InsufficientBankrollError
        self.bankroll -= amount

    def buy_insurance_for_first_hand(self):
        first_hand = self.first_hand() 
        insurance_amount = first_hand.wager / 2  # Insurance is 1/2 the amount wagered on the hand
        try:      
            self._subtract_bankroll(insurance_amount)  
            first_hand.insurance = insurance_amount
            print(f"${insurance_amount} insurance wager placed.")
        except InsufficientBankrollError:
            raise

    def zero_auto_wager(self):
        self.auto_wager = 0

    def set_new_auto_wager(self, auto_wager):
        # Make sure bankroll is large enough
        if auto_wager > self.bankroll:
            raise InsufficientBankrollError
        self.auto_wager = auto_wager

    def set_new_auto_wager_from_input(self, retries=3):
    
        # Set their auto_wager to $0
        self.zero_auto_wager()

        # Ask them for a new auto wager and set it, with some validation
        attempts = 0
        success = False        
        while not success and attempts < retries:
            # This validates that they've entered a float
            new_auto_wager = get_user_input(f"Please enter an auto-wager amount (Bankroll: ${self.bankroll}; enter $0 to cash out): $", float_response)
            
            # This validates that they've entered a wager <= their bankroll
            try:
                self.set_new_auto_wager(new_auto_wager)
                success = True
            except InsufficientBankrollError:
                print('Insufficient bankroll to place that wager. Please try again.')
                attempts += 1

        # If they've unsuccessfully tried to enter input the maximum number of times, exit the program
        if attempts == retries and not success:
            max_retries_exit()

    def print_hands(self):

        for hand in self.hands():
            # Get possible hand total(s) to display
            low_total, high_total = hand.possible_totals()

            # There will always be a low total. If there is a high total, display that too.
            if high_total:
                print(f"Hand (${hand.wager}): {hand} -- ({low_total} or {high_total})")
            else:
                print(f"Hand (${hand.wager}): {hand} -- ({low_total})")

    def play_turn(self):
        
        # Print out the gambler's hand(s)
        self.print_hands()

        response = input("\nWhat would you like to do?\n[ hit (h), stand (s), double (d), split (x) ] => ")


class Dealer(Player):

    def __init__(self, name='Dealer'):
        super().__init__(name)

    def hand(self):
        # The dealer will only ever have a single hand
        return self.hands()[0]

    def up_card(self):
        return self.hand().cards()[0]

    def print_up_card(self):
        print(f"Dealer's Up Card: {self.up_card()} -- ({self.up_card().value})")

    def is_showing_ace(self):
        return self.up_card().name == 'Ace'

    def is_showing_ace_or_face_card(self):
        return self.is_showing_ace() or self.up_card().value == 10

    def print_hand(self):

        hand = self.hand()

        # Get possible hand total(s) to display
        low_total, high_total = hand.possible_totals()

        # There will always be a low total. If there is a high total, display that too.
        if high_total:
            print(f"Hand: {hand} -- ({low_total} or {high_total})")
        else:
            print(f"Hand: {hand} -- ({low_total})")
