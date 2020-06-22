from collections import OrderedDict
from functools import partial
from time import sleep

from blackjack.exc import InsufficientBankrollError
from blackjack.models.hand import DealerHand, GamblerHand
from blackjack.user_input import choice_response, float_response, get_user_input, max_retries_exit, yes_no_response
from blackjack.utils import clear, header


class GameController:

    def __init__(self, gambler, dealer, shoe):
        self.gambler = gambler
        self.dealer = dealer
        self.shoe = shoe

    def check_gambler_wager(self):
        """
        Pre-turn vetting of the gambler's wager.
        1. Check whether the gambler has enough bankroll to place their auto-wager. If not, make them enter a new one.
        2. Ask the gambler if they'd like to change their auto-wager or cash out. Allow them to do so.
        """
        # Check if the gambler still has sufficient bankroll to place the auto-wager
        if self.gambler.can_place_auto_wager():

            # Ask if the gambler wants to cash out or change their auto-wager
            response = get_user_input(
                f"{self.gambler.name}, change your auto-wager or cash out? (Bankroll: ${self.gambler.bankroll}; Auto-Wager: ${self.gambler.auto_wager}) (y/n) => ", 
                yes_no_response
            )
            
            # If they want to make a change, make it
            if response == 'yes':
                self.set_new_auto_wager_from_input()

        # If they don't have sufficient bankroll to place auto-wager, force them to set a new one.
        else:
            print(f"Insufficient bankroll to place current auto-wager (Bankroll: ${self.gambler.bankroll}; Auto-Wager: ${self.gambler.auto_wager})")
            self.set_new_auto_wager_from_input()

    def set_new_auto_wager_from_input(self, retries=3):
        """Set a new auto-wager amount from user input (with input vetting and retry logic)."""
        # Set their auto_wager to $0
        self.gambler.zero_auto_wager()

        # Ask them for a new auto wager and set it, with some validation
        attempts = 0
        success = False        
        while not success and attempts < retries:
            # This validates that they've entered a float
            new_auto_wager = get_user_input(f"Please enter an auto-wager amount (Bankroll: ${self.gambler.bankroll}; enter $0 to cash out): $", float_response)
            
            # This validates that they've entered a wager <= their bankroll
            try:
                self.gambler.set_new_auto_wager(new_auto_wager)
                success = True
            except InsufficientBankrollError as e:
                print(f"{e}. Please try again.")
                attempts += 1

        # If they've unsuccessfully tried to enter input the maximum number of times, exit the program
        if attempts == retries and not success:
            max_retries_exit()

    def deal(self):
        """Deal cards from the Shoe to both the gambler and the dealer to form their initial hands."""
        # Deal 4 cards from the shoe
        card_1, card_2, card_3, card_4 = self.shoe.deal_n_cards(4)

        # Create the Hands from the dealt cards.
        # Deal like they do a casinos --> one card to each player at a time, starting with the gambler.
        gambler_hand = GamblerHand(cards=[card_1, card_3])
        dealer_hand = DealerHand(cards=[card_2, card_4])
        
        # Assign the dealt hands appropriately
        self.gambler.hands.append(gambler_hand)
        self.dealer.hand = dealer_hand

    def play_gambler_turn(self):
        """Play the gambler's turn, meaning play all of the gambler's hands to completion."""
        
        print(f"Playing {self.gambler.name}'s turn.")
        
        # Use a while loop due to the fact that self.hands can grow while iterating (via splitting)
        while any(hand.status == 'Pending' for hand in self.gambler.hands):
            hand = next(hand for hand in self.gambler.hands if hand.status == 'Pending')  # Grab the next unplayed hand
            self.play_gambler_hand(hand)
        
        # Return True if the dealer's hand needs to be played, False otherwise
        return any(hand.status in ('Doubled', 'Stood') for hand in self.gambler.hands)

    def play_gambler_hand(self, hand):
        """Play a gambler hand."""
        # Set the hand's status to 'Playing', and loop until this status changes.
        hand.status = 'Playing'

        # Print the table to show which hand is being played
        self.print_table()

        while hand.status == 'Playing':

            # If the hand resulted from splitting, hit it automatically.
            if len(hand.cards) == 1:
                
                print('Adding second card to split hand...')
                self.hit_hand(hand)

                # Split Aces only get 1 more card.
                if hand.cards[0].is_ace():
                    if hand.is_blackjack():
                        hand.status = 'Blackjack'
                    else:
                        hand.status = 'Stood'
                    break

            # Get the gambler's action from input
            action = self.get_gambler_hand_action(hand)

            if action == 'Hit':
                print('Hitting...')    # Deal another card and keep playing the hand.
                self.hit_hand(hand)

            elif action == 'Stand':
                print('Stood.')        # Do nothing, hand is played.
                hand.status = 'Stood'

            elif action == 'Double':
                print('Doubling...')   # Deal another card and print. Hand is played.
                self.double_hand(hand)
                hand.status = 'Doubled'

            elif action == 'Split':
                print('Splitting...')  # Put the second card into a new hand and keep playing this hand
                self.split_hand(hand)
                continue

            else:
                raise Exception('Unhandled response.')  # Should never get here

            # If the hand is 21 or busted, the hand is done being played.
            if hand.is_21():
                print('21!')
                hand.status = 'Stood'
            elif hand.is_busted():
                print('Busted!')
                hand.status = 'Busted'

            # Print the outcome of the gambler's action
            self.print_table()

    def get_gambler_hand_action(self, hand):
        """List action options for the user on the hand, and get their choice."""
        # Default options that are always available
        options = OrderedDict([('h', 'Hit'), ('s', 'Stand')])

        # Add the option to double if applicable
        if hand.is_doubleable() and self.gambler.can_place_wager(hand.wager):
            options['d'] = 'Double'

        # Add the option to split if applicable
        if hand.is_splittable() and self.gambler.can_place_wager(hand.wager):
            options['x'] = 'Split'

        # Formatted options to display to the user
        display_options = [f"{option} ({abbreviation})" for abbreviation, option in options.items()]

        # Separate out user actions under a new heading
        print(header('ACTIONS'))

        # Ask what the user would like to do, given their options
        response = get_user_input(
            f"\n[ Hand {hand.hand_number} ] What would you like to do? [ {' , '.join(display_options)} ] => ",
            partial(choice_response, choices=options.keys())
        )

        # Return the user's selection ('hit', 'stand', etc.)
        return options[response]

    def hit_hand(self, hand):
        """Add a card to a hand from the shoe."""
        card = self.shoe.deal_card()  # Deal a card
        hand.cards.append(card)  # Add the card to the hand

    def split_hand(self, hand):
        """Split a hand."""
        split_card = hand.cards.pop(1)  # Pop the second card off the hand to make a new hand
        new_hand = GamblerHand(cards=[split_card], hand_number=len(self.gambler.hands) + 1)  # TODO: Do away with hand_number
        self.gambler.place_hand_wager(hand.wager, new_hand)  # Place the same wager on the new hand
        self.gambler.hands.append(new_hand)  # Add the hand to the gambler's list of hands

    def double_hand(self, hand):
        self.gambler.place_hand_wager(hand.wager, hand)  # Double the wager on the hand
        self.hit_hand(hand)  # Add another card to the hand from the shoe

    def play_dealer_turn(self):
        
        print("Playing the Dealer's turn.")

        # Grab the dealer's lone hand to be played
        hand = self.dealer.hand

        # Set the hand's status to 'Playing', and loop until this status changes.
        hand.status = 'Playing'

        self.print_table(hide_dealer=False, dealer_playing=True)
        sleep(2)

        while hand.status == 'Playing':

            # Get the hand total
            total = hand.final_total()

            # Dealer hits under 17 and must hit a soft 17.
            if total < 17 or (total == 17 and hand.is_soft()):
                print('Hitting...')
                self.hit_hand(hand)
            
            # Dealer stands at 17 and above
            else:
                print('Stood.')
                hand.status = 'Stood'

            # If the hand is busted, it's over. Otherwise, sleep so the user can see the card progression
            if hand.is_busted():
                print('Busted!')
                hand.status = 'Busted'
            
            self.print_table(hide_dealer=False, dealer_playing=True)
            sleep(2)

    @staticmethod
    def wants_even_money():
        return get_user_input("Take even money? (y/n) => ", yes_no_response)

    @staticmethod
    def wants_insurance():
        return get_user_input("Insurance? (y/n) => ", yes_no_response)

    def discard_hands(self):
        self.gambler.discard_hands()
        self.dealer.discard_hand()

    def play_pre_turn(self):
        """
        Carry out pre-turn flow for blackjacks, insurance, etc.
        TODO: Refactor into smaller pieces! Not 100% DRY either right now.
        """
        # Grab the gambler's dealt hand
        gambler_hand = self.gambler.first_hand()

        # Check if the gambler has blackjack
        gambler_has_blackjack = gambler_hand.is_blackjack()
        if gambler_has_blackjack:
            print(f"{self.gambler.name} has blackjack.")

        # Dealer can only have blackjack (which ends the turn) if they are showing a face card (value=10) or an ace.
        if self.dealer.is_showing_ace() or self.dealer.is_showing_face_card():

            # Check if the dealer has blackjack, but don't display it to the gambler yet.
            dealer_has_blackjack = self.dealer.hand.is_blackjack()

            # Insurance comes into play if the dealer's upcard is an ace
            if self.dealer.is_showing_ace():

                print('Dealer is showing an Ace.')

                # If the gambler has blackjack, they can either take even money or let it ride.
                if gambler_has_blackjack:

                    if self.wants_even_money() == 'yes':
                        # Pay out even money (meaning 1:1 hand wager)
                        print(f"{self.gambler.name} wins even money.")
                        self.pay_out_hand(gambler_hand, 'wager')
                    else:
                        if dealer_has_blackjack:
                            # Both players have blackjack. Gambler reclaims their wager and that's all.
                            print('Dealer has blackjack. Hand is a push.')
                            self.pay_out_hand(gambler_hand, 'push')
                        else:
                            # Dealer does not have blackjack. Gambler has won a blackjack (which pays 3:2)
                            print(f"Dealer does not have blackjack. {self.gambler.name} wins 3:2.")
                            self.pay_out_hand(gambler_hand, 'blackjack')

                    # The turn is over no matter what if the gambler has blackjack
                    return 'turn over'

                # If the gambler does not have blackjack they can buy insurance.
                else:
                    # Gambler must have sufficient bankroll to place an insurance bet.
                    gambler_can_afford_insurance = self.gambler.can_place_insurance_wager()

                    if gambler_can_afford_insurance and self.wants_insurance() == 'yes':

                        # Insurnace is a side bet that is half their wager, and pays 2:1 if dealer has blackjack.
                        self.gambler.place_insurance_wager()            

                        # The turn is over if the dealer has blackjack. Otherwise, continue on to playing the hand.
                        if dealer_has_blackjack:
                            print(f"Dealer has blackjack. {self.gambler.name}'s insurnace wager wins 2:1 but hand wager loses.")
                            self.gambler.first_hand().payout('insurance', '2:1')
                            return 'turn over'
                        else:
                            print(f"Dealer does not have blackjack. {self.gambler.name}'s insurance wager loses.")
                            return 'play turn'

                    # If the gambler does not (or cannot) place an insurance bet, they lose if the dealer has blackjack. Otherwise, hand continues.
                    else:
                        if not gambler_can_afford_insurance:
                            print('Insufficient bankroll to place insurance wager.')

                        if dealer_has_blackjack:
                            print(f"Dealer has blackjack. {self.gambler.name} loses the hand.")
                            return 'turn over'
                        else:
                            print('Dealer does not have blackjack.')
                            return 'play turn'

            # If the dealer's upcard is a face card, insurance is not in play but need to check if the dealer has blackjack.
            else:
                print('Checking if the dealer has blackjack...')

                # If the dealer has blackjack, it's a push if the player also has blackjack. Otherwise, the player loses.
                if dealer_has_blackjack:

                    print('Dealer has blackjack.')

                    if gambler_has_blackjack:
                        print('Hand is a push.')
                        self.pay_out_hand(gambler_hand, 'push')
                    else:
                        print(f"{self.gambler.name} loses the hand.")
                        
                    # The turn is over no matter what if the dealer has blackjack
                    return 'turn over'

                # If dealer doesn't have blackjack, the player wins if they have blackjack. Otherwise, play the turn.
                else:
                    print('Dealer does not have blackjack.')
                    
                    if gambler_has_blackjack:
                        print(f"{self.gambler.name} wins 3:2.")
                        self.pay_out_hand(gambler_hand, 'blackjack')
                        return 'turn over'
                    else:
                        return 'play turn'

        # If the dealer's upcard is not an ace or a face card, they cannot have blackjack.
        # If the player has blackjack here, payout 3:2 and the hand is over. Otherwise, continue with playing the hand.
        else:
            if gambler_has_blackjack:
                print(f"{self.gambler.name} wins 3:2.")
                self.pay_out_hand(gambler_hand, 'blackjack')
                return 'turn over'
            else:
                return 'play turn'

    def pay_out_hand(self, hand, payout_type):
        
        # Pay out winning hand wagers 1:1 and reclaim the wager
        if payout_type == 'wager':
            self.perform_hand_payout(hand, 'winning_wager', '1:1')
            self.perform_hand_payout(hand, 'wager_reclaim')
        
        # Pay out winning blackjack hands 3:2 and reclaim the wager
        elif payout_type == 'blackjack':
            self.perform_hand_payout(hand, 'winning_wager', '3:2')
            self.perform_hand_payout(hand, 'wager_reclaim')

        # Pay out winning insurance wagers 2:1 and reclaim the insurance wager
        elif payout_type == 'insurance':
            self.perform_hand_payout(hand, 'winning_insurance', '2:1')
            self.perform_hand_payout(hand, 'insurance_reclaim')
        
        # Reclaim wager in case of a push
        elif payout_type == 'push':
            self.perform_hand_payout(hand, 'wager_reclaim')
        
        # Should not get here
        else:
            raise ValueError(f"Invalid payout type: '{payout_type}'")

    def perform_hand_payout(self, hand, payout_type, odds=None):

        # Validate args passed in
        if payout_type in ('winning_wager', 'winning_insurance'):
            assert odds, 'Must specify odds for wager and insurance payouts!'
            antecedent, consequent = map(int, odds.split(':'))
        
        # Determine the payout amount by the payout_type (and odds if applicable)
        if payout_type == 'winning_wager':
            amount = hand.wager * antecedent / consequent
            message = f"Adding winning hand payout of ${amount} to bankroll."
        
        elif payout_type == 'wager_reclaim':
            amount = hand.wager
            message = f"Reclaiming hand wager of ${amount}."
        
        elif payout_type == 'winning_insurance':
            amount = hand.insurance * antecedent / consequent
            message = f"Adding winning insurance payout of ${amount} to bankroll."
        
        elif payout_type == 'insurance_reclaim':
            amount = hand.insurance
            message = f"Reclaiming insurance wager of ${amount}."

        else:
            raise ValueError(f"Invalid payout type: '{payout_type}'")

        self.gambler.payout(amount)
        print(message)

    def settle_hand(self, hand):
        """Settle any outstanding wagers on a hand (relative to the dealer's hand)."""
        
        print(f"\n[ Hand {hand.hand_number} ]")

        # If the gambler's hand is busted, it's a loss regardless
        if hand.status == 'Busted':
            print('Outcome: LOSS')
            print(f"${hand.wager} hand wager lost.")

        # If the dealer's hand is busted, it's a win (given that we've already checked for gambler hand bust)
        elif self.dealer.hand.status == 'Busted':
            print('Outcome: WIN')
            self.pay_out_hand(hand, 'wager')
        
        # If neither gambler nor dealer hand is busted, compare totals to determine wins and losses.
        else:
            hand_total = hand.final_total()
            dealer_hand_total = self.dealer.hand.final_total()

            if hand_total > dealer_hand_total:
                print('Outcome: WIN')
                self.pay_out_hand(hand, 'wager')
            elif hand_total == dealer_hand_total:
                print('Outcome: PUSH')
                self.pay_out_hand(hand, 'push')
            else:
                print('Outcome: LOSS')
                print(f"${hand.wager} hand wager lost.")

    def settle_up(self):
        print('Settling up.')
        # For each of the gambler's hands, settle wagers against the dealer's hand
        for hand in self.gambler.hands:
            self.settle_hand(hand)

    def print_table(self, hide_dealer=True, dealer_playing=False):

        # Clear terminal output to reprint the table
        clear()  # NOTE: Eventually come up with a better solution

        print(header('TABLE'))

        # Print the dealer's hand. If `hide_dealer` is True, don't factor in the dealer's buried card.
        num_dashes = len(self.dealer.name) + 6
        print(f"{'-'*num_dashes}\n   {self.dealer.name.upper()}   \n{'-'*num_dashes}\n")
        print(self.dealer.hand.pretty_format(hide_burried_card=hide_dealer))

        # Print the gambler's hand(s)
        num_dashes = len(self.gambler.name) + 6
        print(f"\n{'-'*num_dashes}\n   {self.gambler.name.upper()}   \n{'-'*num_dashes}\n\nBankroll: ${self.gambler.bankroll}")
        for hand in self.gambler.hands:
            print(hand.pretty_format())
        print()

        if dealer_playing:
            print("Playing the Dealer's turn...")

    def finalize_turn(self):
        # Discard both the gambler and the dealer's hands.
        self.discard_hands()
        # Pause exectution until the user wants to proceed.
        input('\n\nPush ENTER to proceed => ')

    def play(self):

        while not self.gambler.is_finished():

            print(header('NEW TURN'))

            # Vet the gambler's auto-wager against their bankroll, and ask if they would like to change their wager or cash out.
            self.check_gambler_wager()
            if self.gambler.is_finished():  # If they cashed out, don't play the turn. The game is over.
                return

            # Deal 2 cards from the shoe to the gambler's and the dealer's hands. Place the gambler's auto-wager on the hand.
            self.deal()

            # Place the gambler's auto-wager on the hand. We've already vetted that they have sufficient bankroll.
            self.gambler.place_auto_wager()

            # Print the table, hiding the dealer's buried card from the gambler
            self.print_table()

            # Carry out pre-turn flow (for blackjacks, insurance, etc). If either player had blackjack, there is no turn to play.
            result = self.play_pre_turn()
            if result == 'turn over':
                self.finalize_turn()
                continue

            # Play the gambler's turn.
            play_dealer_turn = self.play_gambler_turn()
            
            # Play the dealer's turn if necessary
            if play_dealer_turn:
                self.play_dealer_turn()

            # # Print the final table, showing the dealer's cards.
            # self.print(hide_dealer=False)

            # print(header('OUTCOMES'))

            # Settle gambler hand wins and losses.
            self.settle_up()

            # Discard hands and pause execution until the user elects to proceed with the next turn.
            self.finalize_turn()
