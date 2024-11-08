import sqlite3
import getpass
from datetime import timedelta, datetime, date
import sys

# Global variables
connection = None
cursor = None
login_user = None

def connect(db_name):
    """Connect to the SQLite database."""
    global connection, cursor
    connection = sqlite3.connect(db_name)
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    connection.commit()

def login():
    """Login to the system."""
    global login_user
    email = input("Enter your email: ").strip()
    password = getpass.getpass("Enter your password: ")

    cursor.execute("SELECT * FROM members WHERE UPPER(email) = ? AND passwd = ?", (email.upper(), password))
    user = cursor.fetchone()

    if user is None:
        print("Invalid email or password.")
    else:
        print("Logged in successfully.")
        login_user = email

def signup():
    """Signup to the system."""
    email = input("Enter your email: ").strip() # Remove leading/trailing spaces
    cursor.execute("SELECT * FROM members WHERE UPPER(email) = ?", (email.upper(),)) 
    user = cursor.fetchone()
    # Check if the user already exists
    if user:
        print("User already exists.")
        return
    
    # Get user information
    password = getpass.getpass("Enter your password: ")
    name = input("Enter your name: ")
    birth_year = int(input("Enter your birth year: "))
    faculty = input("Enter your faculty name: ")

    # Insert the new user into the database
    cursor.execute("INSERT INTO members VALUES (?, ?, ?, ?, ?)", (email, password, name, birth_year, faculty))
    connection.commit()

    print("Signed up successfully. You can now log in.")

def logout():
    """Logout from the system."""
    global login_user
    login_user = None
    print("Logged out successfully.\n")

def view_profile():
    """View user profile."""
    global login_user
    if not login_user:
        print("You are not logged in.")
        return

    # Fetch personal information
    cursor.execute("SELECT name, email, byear FROM members WHERE UPPER(email) = ?", (login_user.upper(),))
    user = cursor.fetchone()
    if not user:
        print("User not found.")
        return
    name, email, byear = user
    print(f"\n----- Personal Information -----\nName: {name}\nEmail: {email}\nBirth Year: {byear}")

    # Fetch borrowing information
    cursor.execute("SELECT COUNT(*), COUNT(CASE WHEN end_date IS NULL THEN 1 END), COUNT(CASE WHEN end_date IS NULL AND start_date < ? THEN 1 END) FROM borrowings WHERE member = ?", (date.today() - timedelta(days=20), login_user))
    total_borrowings, current_borrowings, overdue_borrowings = cursor.fetchone()
    print(f"\n----- Borrowing Information -----\nTotal Borrowings: {total_borrowings}\nCurrent Borrowings: {current_borrowings}\nOverdue Borrowings: {overdue_borrowings}")

    # Fetch penalty information
    cursor.execute("SELECT COUNT(*), SUM(amount - IFNULL(paid_amount, 0)) FROM penalties WHERE bid IN (SELECT bid FROM borrowings WHERE member = ?) AND amount > IFNULL(paid_amount, 0)", (login_user,))
    unpaid_penalties, total_debt = cursor.fetchone()
    cursor.execute("""
        SELECT start_date
        FROM borrowings
        WHERE member = ? AND end_date IS NULL
        """, (login_user,))

    # Fetch borrowings
    borrowings = cursor.fetchall()
    dues = 0
    penaltyBorrowings = 0

    # Calculate the dues and penaltyBorrowings
    for borrowing in borrowings:
        start_date = datetime.strptime(borrowing[0], '%Y-%m-%d').date() # Convert the string to a date object
        is_leap_year = (start_date.year % 4 == 0 and (start_date.year % 100 != 0 or start_date.year % 400 == 0))
        due_date = start_date + timedelta(days=20 if start_date.month != 2 or is_leap_year else 19)  # 20 days borrowing period, adjusting for leap year February
        days_late = (date.today() - due_date).days if date.today() > due_date else 0 # Calculate the days late
        dues += days_late * 1  # $1 per day

        # If the book is overdue, increment the penaltyBorrowings
        if date.today() > due_date:
            penaltyBorrowings += 1

    # Add the penaltyBorrowings to the unpaid_penalties
    unpaid_penalties += penaltyBorrowings

    if total_debt == None:
        total_debt = 0

    print(f"\n----- Penalty Information -----\nUnpaid Penalties: {unpaid_penalties}\nTotal Debt: ${round(total_debt + dues, 2):.2f} (including unreturned books)\n")
    
def return_book():
    """Return a book."""
    global login_user
    if not login_user:
        print("You are not logged in.")
        return

    # Fetch current borrowings
    cursor.execute("""
        SELECT br.bid, b.title, br.start_date
        FROM borrowings AS br
        JOIN books AS b ON br.book_id = b.book_id
        WHERE br.member = ? AND br.end_date IS NULL
        """, (login_user,))
    borrowings = cursor.fetchall()
    
    if not borrowings:
        print("You have no current borrowings.")
        return
    
    # Display current borrowings and calculate dues
    for i, borrowing in enumerate(borrowings):
        start_date = datetime.strptime(borrowing[2], '%Y-%m-%d').date()
        is_leap_year = (start_date.year % 4 == 0 and (start_date.year % 100 != 0 or start_date.year % 400 == 0))
        due_date = start_date + timedelta(days=20 if start_date.month != 2 or is_leap_year else 19)  # 20 days borrowing period, adjusting for leap year February
        days_late = (date.today() - due_date).days if date.today() > due_date else 0
        dues = days_late * 1  # $1 per day
        print(f"{i+1}. ID: {borrowing[0]}, Title: '{borrowing[1]}', Borrowed on: {borrowing[2]}, Dues: ${dues}")
    
    # Ask the user to select a borrowing to return
    while True:
        bid_input = input("Enter the borrowing ID to return or press enter to exit: ")
        if bid_input == "":
            return
        try:
            bid = int(bid_input)
            if bid in [b[0] for b in borrowings]:
                break
            else:
                print("Invalid borrowing ID.")
        except ValueError:
            print("Invalid input.")


    # Create a date string in the format SQLite understands (YYYY-MM-DD)
    today_date = date.today().isoformat()

    # Use the date string in your query
    cursor.execute("UPDATE borrowings SET end_date = ? WHERE bid = ?", (today_date, bid))
    
    if days_late > 0:
        cursor.execute("INSERT INTO penalties (bid, amount, paid_amount) VALUES (?, ?, 0)", (bid, dues))
    
    connection.commit()

    print("Book returned successfully.")

    # Ask the user to write a review
    if input("Would you like to write a review? (y/n): ").lower() == "y":
        while True:
            try:
                rating = int(input("Rating (1-5): "))
                if rating < 1 or rating > 5:
                    print("Invalid rating. Please enter a number between 1 and 5.")
                    continue
                text = input("Review text: ")
                cursor.execute("INSERT INTO reviews (book_id, member, rating, rtext, rdate) VALUES ((SELECT book_id FROM borrowings WHERE bid = ?), ?, ?, ?, ?)", (bid, login_user, rating, text, date.today()))
                connection.commit()
                print("Review added successfully.")
                break
            except ValueError:
                print("Invalid input for rating.")

def search_book():
    """Search for a book."""
    global login_user
    if not login_user:
        print("You are not logged in.")
        return
    
    # Ask the user for a keyword to search for
    keyword = input("Enter a keyword to search for books: ")
    keyword = f'%{keyword.strip().upper()}%'  # Use strip to remove leading/trailing spaces and upper for case-insensitivity

    # Fetch books matching the keyword
    page = 1
    page_size = 5
    while True:
        offset = (page - 1) * page_size

        query = """
        SELECT book_id, title, author, pyear,
               (SELECT AVG(rating) 
               FROM reviews WHERE book_id = b.book_id) as avg_rating, 
               (CASE WHEN EXISTS (SELECT 1 FROM borrowings 
               WHERE book_id = b.book_id AND end_date IS NULL) 
               THEN 'Borrowed' ELSE 'Available' END) as status
        FROM books b
        WHERE UPPER(TRIM(title)) LIKE ? OR UPPER(TRIM(author)) LIKE ?
        ORDER BY 
            CASE WHEN UPPER(TRIM(title)) LIKE ? THEN 1 ELSE 2 END,
            CASE WHEN UPPER(TRIM(title)) LIKE ? THEN UPPER(TRIM(title)) ELSE UPPER(TRIM(author)) END
        LIMIT ? OFFSET ?
        """

        # Use the query to fetch books
        cursor.execute(query, (keyword, keyword, keyword, keyword, page_size, offset))
        results = cursor.fetchall()

        if not results:
            print("No more books to display.")
            break

        # Display the books
        for result in results:
            print(f"ID: {result[0]}, Title: {result[1]}, Author: {result[2]}, Year: {result[3]}, Avg. Rating: {result[4] if result[4] else 'N/A'}, Status: {result[5]}")

        # Offer to borrow a book if available
        if any(result[5] == 'Available' for result in results):
            book_id_to_borrow = input("Enter the book ID to borrow or press enter to continue: ").strip()
            if book_id_to_borrow:
                borrow_book(book_id_to_borrow)

        # Ask the user if they want to see more books
        if len(results) < page_size:
            print("No more books to display.")
            break

        #  Ask the user if they want to see more books
        print("More books are available. Do you want to see the next page? (yes/no)")
        if input().lower() != 'yes':
            break
        
        page += 1

def borrow_book(book_id):
    """Borrow a book."""
    member_email = login_user  # Assuming the user is logged in and login_user contains the user's email

    # Check if the book is already borrowed
    cursor.execute("SELECT 1 FROM borrowings WHERE book_id = ? AND end_date IS NULL", (book_id,))
    if cursor.fetchone():
        print("This book is currently borrowed and cannot be borrowed again.")
        return

    # Insert a new borrowing entry
    cursor.execute("INSERT INTO borrowings (member, book_id, start_date) VALUES (?, ?, ?)", (member_email, book_id, date.today()))
    connection.commit()
    print(f"Book {book_id} borrowed successfully.")


def pay_penalty():
    """Pay a penalty."""
    global login_user
    if not login_user:
        print("You are not logged in.")
        return

    # Fetch unpaid penalties for the user
    cursor.execute("""
        SELECT p.pid, p.amount, IFNULL(p.paid_amount, 0), (p.amount - IFNULL(p.paid_amount, 0)) AS due
        FROM penalties p
        JOIN borrowings b ON p.bid = b.bid
        WHERE b.member = ? AND p.amount > IFNULL(p.paid_amount, 0)
    """, (login_user,))
    penalties = {penalty[0]: penalty[1:] for penalty in cursor.fetchall()}

    if not penalties:
        print("You have no unpaid penalties.")
        return
    
    # Display unpaid penalties
    print("Unpaid Penalties:")
    for pid, penalty in penalties.items():
        amount, paid, due = penalty
        print(f"\nPenalty ID: {pid}\nAmount: ${round(amount, 2):.2f}\nPaid: ${round(paid, 2):.2f}\nDue: ${round(due, 2):.2f}\n{'-'*40}")  # Rounded values

    # Ask the user to select a penalty to pay
    while True:
        try:
            pid = int(input("Enter the Penalty ID you wish to pay: "))
            if pid not in penalties:
                raise ValueError
            break
        except ValueError:
            print("Invalid selection.")

    # Ask the user to enter the payment amount
    amount, paid, due = penalties[pid]
    while True:
        try:
            payment_amount = round(float(input(f"Enter payment amount for Penalty ID {pid} (Due: ${round(due, 2)}): ")), 2)
            if payment_amount <= 0 or payment_amount > round(due,2):
                raise ValueError
            break
        except ValueError:
            print("Invalid payment amount.")

    # Update the penalty record with the new payment
    new_paid_amount = round(paid + payment_amount, 2)
    cursor.execute("UPDATE penalties SET paid_amount = ? WHERE pid = ?", (new_paid_amount, pid))

    connection.commit()
    print(f"Payment of ${payment_amount} applied to Penalty ID {pid}.")

def main(db_name):
    global login_user
    connect(db_name)

    while True:
        # User Interface
        if login_user is None:
            print("Login\nSignup\nExit")
        else:
            print("\nView Profile\nReturn Book\nSearch Book\nPay Penalty\nLogout\nExit")

        choice = input("Enter your choice: ").lower().strip()

        # Before login
        if not login_user:
            if choice == "login":
                login()
            elif choice == "signup":
                signup()
            elif choice == "exit":
                break  
            else:
                print("Invalid input. Please try again.\n")

        # After login
        else:
            if choice == "view profile":
                view_profile()
            elif choice == "return book":
                return_book()
            elif choice == "search book":
                search_book()
            elif choice == "pay penalty":
                pay_penalty()
            elif choice == "logout":
                logout()
            elif choice == "exit":
                break  
            else:
                print("Invalid input. Please try again.")

if __name__ == "__main__":
    # Check for the correct number of command-line arguments
    if len(sys.argv) != 2:
        print("Usage: python database.py <database_name>")
        sys.exit(1)
        
    # Call the main function
    db_name = sys.argv[1]
    main(db_name)
